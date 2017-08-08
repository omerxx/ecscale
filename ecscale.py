#!/bin/python
import boto3
import datetime

SCALE_IN_CPU_TH = 30
SCALE_IN_MEM_TH = 60
FUTURE_MEM_TH = 75


def clusters(ecsClient, type='Name'):
    # Returns an iterable list of cluster names
    response = ecsClient.list_clusters()
    if not response['clusterArns']:
        print 'No ECS cluster found'
        exit

    return [cluster.split('/')[1] for cluster in response['clusterArns']] if type == 'Name' else [cluster for cluster in response['clusterArns'] if 'awseb' not in cluster]


def cluster_memory_reservation(cwClient):
    # Return cluster mem reservation average per minute cloudwatch metric
    response = cwClient.get_metric_statistics( 
        Namespace='AWS/ECS',
        MetricName='MemoryReservation',
        Dimensions=[
            {
                'Name': 'ClusterName',
                'Value': 'prod-machine'
            },
        ],
        StartTime=datetime.datetime.utcnow() - datetime.timedelta(seconds=120),
        EndTime=datetime.datetime.utcnow(),
        Period=60,
        Statistics=['Average']
    )

    return response['Datapoints'][0]['Average']


def find_asg(clusterName, asgClient):
    # Returns auto scaling group resourceId based on name
    response = asgClient.describe_auto_scaling_groups()
    for asg in response['AutoScalingGroups']:
        for tag in asg['Tags']:
            if tag['Key'] == 'Name':
                if tag['Value'].split(' ')[0] == clusterName:
                    return tag['resourceid']

    else:
        print 'auto scaling group for {} not found. exiting'.format(cluster)
        exit


def ec2_avg_cpu_utilization(clusterName, asgclient, cwclient):
    asg = find_asg(clusterName, asgclient)
    response = cwclient.get_metric_statistics( 
        namespace='aws/ec2',
        metricname='cpuutilization',
        dimensions=[
            {
                'name': 'autoscalinggroupname',
                'value': asg
            },
        ],
        starttime=datetime.datetime.utcnow() - datetime.timedelta(seconds=120),
        endtime=datetime.datetime.utcnow(),
        period=60,
        statistics=['average']
    )
    return response['datapoints'][0]['average']


def empty_instances(clusterArn, activeContainerDescribed):
    # returns a list of empty instances in cluster
    instances = []
    empty_instances = []

    for inst in activeContainerDescribed['containerInstances']:
        if inst['runningTasksCount'] == 0 and inst['pendingTasksCount'] == 0:
            empty_instances.append(inst['ec2InstanceId'])

    return empty_instances


def draining_instances(clusterArn, drainingContainerDescribed):
    # returns a list of draining instances in cluster
    instances = []
    draining_instances = []

    for inst in drainingContainerDescribed['containerInstances']:
        draining_instances.append(inst['ec2InstanceId'])

    return draining_instances


def terminate_decrease(instanceId, asgClient):
    # terminates an instance and decreases the desired number in its auto scaling group
    # [ only if desired > minimum ]
    try:
        response = asgClient.terminate_instance_in_auto_scaling_group(
            InstanceId=instanceId,
            ShouldDecrementDesiredCapacity=True
        )
        print response['Activity']['Cause']

    except Exception as e:
        print 'Termination failed: {}'.format(e)


def scale_in_instance(clusterArn, activeContainerDescribed):
    # iterates over hosts, finds the least utilized:
    # The most under-utilized memory and minimum running tasks
    # return instance obj {instanceId, runningInstances, containerinstanceArn}
    instanceToScale = {'id': '', 'running': 0, 'freemem': 0}
    for inst in activeContainerDescribed['containerInstances']:
        print 'REMAINING' + str(inst['runningTasksCount'])
        for res in inst['remainingResources']:
            if res['name'] == 'MEMORY':
                if res['integerValue'] > instanceToScale['freemem']:
                    instanceToScale['freemem'] = res['integerValue']
                    instanceToScale['id'] = inst['ec2InstanceId']
                    instanceToScale['running'] = inst['runningTasksCount']
                    instanceToScale['containerInstanceArn'] = inst['containerInstanceArn']
                    
                elif res['integerValue'] == instanceToScale['freemem']:
                    # Two instances with same free memory level, choose the one with less running tasks
                    if inst['runningTasksCount'] < instanceToScale['running']:
                        instanceToScale['freemem'] = res['integerValue']
                        instanceToScale['id'] = inst['ec2InstanceId']
                        instanceToScale['running'] = inst['runningTasksCount'] 
                        instanceToScale['containerInstanceArn'] = inst['containerInstanceArn']
                break

    else:
        print 'No active containers'
        exit

    print 'Scale candidate: {}'.format(instanceToScale)
    return instanceToScale

    
def running_tasks(instanceId, activeContainerDescribed):
    # return a number of running tasks on a given ecs host
    for inst in activeContainerDescribed['containerInstances']:
        if inst['ec2InstanceId'] == instanceId:
            return int(inst['runningTasksCount']) + int(inst['pendingTasksCount']) 
    
    else:
        print 'Instance not found'
        exit


def drain_instance(containerInstanceId, ecsClient, clusterArn):
    # put a given ec2 into draining state
    try:
        response = ecsClient.update_container_instances_state(
            cluster=clusterArn,
            containerInstances=[containerInstanceId],
            status='DRAINING'
        )
        print 'Done draining'            

    except Exception as e:
        print 'Draining failed: {}'.format(e) 


def future_reservation(cluster):
    # return cluster_mem_reserve*num_of_ec2 / num_of_ec2-1

    pass


def main():
    ecsClient = boto3.client('ecs')
    cwClient = boto3.client('cloudwatch')
    asgClient = boto3.client('autoscaling')


    for cluster in clusters(ecsclient):
        ## Retrieve container instances data: ##
        activeContainerInstances = ecsClient.list_container_instances(cluster=clusterArn, status='ACTIVE')
        if activeContainerInstances['containerInstanceArns']:
            activeContainerDescribed = ecsClient.describe_container_instances(cluster=clusterArn, containerInstances=activeContainerInstances['containerInstanceArns'])
        else: 
            print 'No active instances in cluster.'
            break
        drainingContainerInstances = ecsClient.list_container_instances(cluster=clusterArn, status='DRAINING')
        if drainingContainerInstances['containerInstanceArns']: 
            drainingContainerDescribed = ecsClient.describe_container_instances(cluster=clusterArn, containerInstances=drainingContainerInstances['containerInstanceArns'])
        else:
            drainingContainerDescribed = []
            print 'No draining containers in cluster'
        ######### End of data retrieval #########


        if empty_instances(cluster):
            for instance in empty_instances(cluster):
                drain_instance(instance)

        if draining_instances(cluster): 
            for instance in draining_instances(cluster):
                if not running_tasks(instance):
                    terminate_decrease(instance)

        if (future_reservation(cluster) < future_mem_th): 
            if (cluster_memory_reservation(cluster) < scale_in_mem_th): 
                if (ec2_avg_cpu_utilization(cluster) < scale_in_cpu_th):
                # cluster hosts can be scaled in
                    drain_instance(scale_in_instance(cluster)['containerInstanceArn'])


if __name__ == '__main__':
    ecsClient = boto3.client('ecs')
    cwClient = boto3.client('cloudwatch')
    asgClient = boto3.client('autoscaling')
    clusterArn = 'arn:aws:ecs:us-east-1:017894670386:cluster/prerender-read' 
    activeContainerInstances = ecsClient.list_container_instances(cluster=clusterArn, status='ACTIVE')
    if activeContainerInstances['containerInstanceArns']:
        activeContainerDescribed = ecsClient.describe_container_instances(cluster=clusterArn, containerInstances=activeContainerInstances['containerInstanceArns'])
        exit
    else:
        print 'No active instances in cluster.'
        
    drainingContainerInstances = ecsClient.list_container_instances(cluster=clusterArn, status='DRAINING')
    if drainingContainerInstances['containerInstanceArns']: 
        drainingContainerDescribed = ecsClient.describe_container_instances(cluster=clusterArn, containerInstances=drainingContainerInstances['containerInstanceArns'])
    else:
        drainingContainerDescribed = []
        print 'No draining containers in cluster'
    
    #main()
    #print clusters(boto3.client('ecs'), type='arn')
    #cluster_memory_reservation(boto3.client('cloudwatch'))

    #ec2_avg_cpu_utilization('prod-machine', boto3.client('autoscaling'), boto3.client('cloudwatch'))
    #print empty_instances('arn:aws:ecs:us-east-1:017894670386:cluster/prod-machine', activeContainerDescribed)
    
    #print clusters(boto3.client('ecs'), type='arn')
    #draining_instances('arn:aws:ecs:us-east-1:017894670386:cluster/prod-machine', boto3.client('ecs'))
    #terminate_decrease('i-06882bc271b0549b6', boto3.client('autoscaling'))
    #print scale_in_instance('arn:aws:ecs:us-east-1:017894670386:cluster/prerender-read', activeContainerDescribed)
    #print running_tasks('i-0a1c7430ffc94f', activeContainerDescribed)
    drain_instance('arn:aws:ecs:us-east-1:017894670386:container-instance/13c7488a-edbf-4843-ac44-a615476aead1', ecsClient, 'arn:aws:ecs:us-east-1:017894670386:cluster/prerender-read')