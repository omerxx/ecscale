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


def empty_instances(clusterArn, ecsClient):
    # returns a list of empty instances in cluster
    instances = []
    empty_instances = []
    response = ecsClient.list_container_instances(cluster=clusterArn, status='ACTIVE')
    for inst in response['containerInstanceArns']:
        instances.append(inst)

    response = ecsClient.describe_container_instances(cluster=clusterArn, containerInstances=instances)
    for inst in response['containerInstances']:
        if inst['runningTasksCount'] == 0 and inst['pendingTasksCount'] == 0:
            empty_instances.append[inst['ec2InstanceId']]

    return empty_instances


def draining_instances(cluster):
    # returns a list of draining instances in cluster
    pass


def terminate_decrease(instanceid):
    # terminates an instance and decreases the desired number in its auto scaling group
    # [ only if desired > minimum ]
    pass


def scale_in(cluster):
    # iterates over hosts, finds the least utilized:
    #### top free memory -> lowest number of tasks
    # drain the instance
    pass


def running_tasks(instance):
    # return a number of running tasks on a given ecs host
    pass


def drain_instance(instance):
    # put a given ec2 into draining state 
    pass


def future_reservation(cluster):
    # return cluster_mem_reserve*num_of_ec2 / num_of_ec2-1
    pass


def main():
    ecsclient = boto3.client('ecs')
    cwclient = boto3.client('cloudwatch')
    asgclient = boto3.client('autoscaling')
    for cluster in clusters(ecsclient):
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
                    scale_in(cluster)            


if __name__ == '__main__':
    #main()
    #clusters(boto3.client('ecs'))
    #cluster_memory_reservation(boto3.client('cloudwatch'))

    #ec2_avg_cpu_utilization('prod-machine', boto3.client('autoscaling'), boto3.client('cloudwatch'))
    empty_instances('arn:aws:ecs:us-east-1:017894670386:cluster/prod-machine', boto3.client('ecs'))
    #print clusters(boto3.client('ecs'), type='arn')






