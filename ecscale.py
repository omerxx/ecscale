#!/bin/python
import boto3
import datetime

SCALE_IN_CPU_TH = 30
SCALE_IN_MEM_TH = 60
FUTURE_MEM_TH = 75
ECS_AVOID_STR = 'awseb'


def clusters(ecsClient):
    # Returns an iterable list of cluster names
    response = ecsClient.list_clusters()
    if not response['clusterArns']:
        print 'No ECS cluster found'
        exit

    return [cluster for cluster in response['clusterArns'] if ECS_AVOID_STR not in cluster]


def cluster_memory_reservation(cwClient, clusterName):
    # Return cluster mem reservation average per minute cloudwatch metric
    try:
        response = cwClient.get_metric_statistics( 
            Namespace='AWS/ECS',
            MetricName='MemoryReservation',
            Dimensions=[
                {
                    'Name': 'ClusterName',
                    'Value': clusterName
                },
            ],
            StartTime=datetime.datetime.utcnow() - datetime.timedelta(seconds=120),
            EndTime=datetime.datetime.utcnow(),
            Period=60,
            Statistics=['Average']
        )
        return response['Datapoints'][0]['Average']

    except Exception as e:
        print 'Could not retrieve mem reservation for {}'.format(clusterName)


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

    # ------------------------------------------------------------>
    # TODO: MAKE THIS RETURN AN OBJECT THAT CONTAINS THE CONTAINER INSTANCE ID TOO!
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
        print 'No active containers in cluster'
    print 'Scale candidate: {}'.format(instanceToScale)
    return instanceToScale

    
def running_tasks(instanceId, activeContainerDescribed):
    # return a number of running tasks on a given ecs host
    for inst in activeContainerDescribed['containerInstances']:
        if inst['ec2InstanceId'] == instanceId:
            return int(inst['runningTasksCount']) + int(inst['pendingTasksCount']) 
    
    else:
        print 'Instance not found'


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


def future_reservation(activeContainerDescribed, clusterMemReservation):
    # If the cluster were to scale in an instance, calculate the effect on mem reservation
    # return cluster_mem_reserve*num_of_ec2 / num_of_ec2-1
    numOfEc2 = len(activeContainerDescribed['containerInstances'])
    futureMem = (clusterMemReservation*numOfEc2) / (numOfEc2-1)
    print 'Current reservation vs Future: {} : {}'.format(clusterMemReservation, futureMem)
    return futureMem


def main():
    ecsClient = boto3.client('ecs')
    cwClient = boto3.client('cloudwatch')
    asgClient = boto3.client('autoscaling')
    clusterList = clusters(ecsClient)

    for cluster in clusterList:
        ## Retrieve container instances data: ##
        clusterName = cluster.split('/')[1]
        print '*** {} ***'.format(clusterName)
        activeContainerInstances = ecsClient.list_container_instances(cluster=cluster, status='ACTIVE')
        clusterMemReservation = cluster_memory_reservation(cwClient, clusterName)
        
        if activeContainerInstances['containerInstanceArns']:
            activeContainerDescribed = ecsClient.describe_container_instances(cluster=cluster, containerInstances=activeContainerInstances['containerInstanceArns'])
        else: 
            print 'No active instances in cluster'
            continue 
        drainingContainerInstances = ecsClient.list_container_instances(cluster=cluster, status='DRAINING')
        if drainingContainerInstances['containerInstanceArns']: 
            drainingContainerDescribed = ecsClient.describe_container_instances(cluster=cluster, containerInstances=drainingContainerInstances['containerInstanceArns'])
        else:
            drainingContainerDescribed = []
            #print 'No draining containers in cluster {}'.format(clusterName)
        emptyInstances = empty_instances(cluster, activeContainerDescribed)
        drainingInstances = draining_instances(cluster)
        ######### End of data retrieval #########


        if emptyInstances:
            for instance in emptyInstances:
                print 'I am draining {}'.format(instance)
                drain_instance(containerInstanceId, ????)

        if drainingInstances: 
            for instance in drainingInstances:
                if not running_tasks(instance):
                    # terminate_decrease(instance)
                    print 'I want to terminate draining instance with no containers {}'.format(instance)

        # if (future_reservation(activeContainerDescribed, clusterMemReservation) < FUTURE_MEM_TH): 
        #     if (clusterMemReservation < SCALE_IN_MEM_TH: 
        #         if (ec2_avg_cpu_utilization(cluster) < SCALE_IN_CPU_TH):
        #         # cluster hosts can be scaled in
        #             drain_instance(scale_in_instance(cluster)['containerInstanceArn'])


if __name__ == '__main__':
    # ecsClient = boto3.client('ecs')
    # cwClient = boto3.client('cloudwatch')
    # asgClient = boto3.client('autoscaling')
    # clusterArn = 'arn:aws:ecs:us-east-1:017894670386:cluster/prerender-read' 
    # activeContainerInstances = ecsClient.list_container_instances(cluster=clusterArn, status='ACTIVE')
    # if activeContainerInstances['containerInstanceArns']:
    #     activeContainerDescribed = ecsClient.describe_container_instances(cluster=clusterArn, containerInstances=activeContainerInstances['containerInstanceArns'])
    #     exit
    # else:
    #     print 'No active instances in cluster.'
        
    # drainingContainerInstances = ecsClient.list_container_instances(cluster=clusterArn, status='DRAINING')
    # if drainingContainerInstances['containerInstanceArns']: 
    #     drainingContainerDescribed = ecsClient.describe_container_instances(cluster=clusterArn, containerInstances=drainingContainerInstances['containerInstanceArns'])
    # else:
    #     drainingContainerDescribed = []
    #     print 'No draining containers in cluster'
        
    # clusterMemReservation = cluster_memory_reservation(cwClient, 'prerender-read')
    

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
    #drain_instance('arn:aws:ecs:us-east-1:017894670386:container-instance/13c7488a-edbf-4843-ac44-a615476aead1', ecsClient, 'arn:aws:ecs:us-east-1:017894670386:cluster/prerender-read')
    #print future_reservation(activeContainerDescribed, clusterMemReservation)

    main() 