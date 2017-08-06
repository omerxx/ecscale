#!/bin/python
import boto3
import datetime

SCALE_IN_CPU_TH = 30
SCALE_IN_MEM_TH = 60
FUTURE_MEM_TH = 75


def clusters(ecsClient):
    # Returns an iterable list of cluster names
    response = ecsClient.list_clusters()
    if not response['clusterArns']:
        print 'No ECS cluster found'
        exit

    return [cluster.split('/')[1] for cluster in response['clusterArns']]


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


def ec2_avg_cpu_utilization(cluster, asgClient):
    response = asgClient.describe_auto_scaling_groups()
    for asg in response['AutoScalingGroups']:
        for tag in asg['Tags']:
            if tag['Key'] == 'Name':
                if tag['Value'].split(' ')[0] == cluster:
                    asgName = asg['AutoScalingGroupARN']
                    print tag['Value']
                    return


def empty_instances(cluster):
    # Returns a list of empty instances in cluster
    pass


def draining_instances(cluster):
    # Returns a list of draining instances in cluster
    pass


def terminate_decrease(instanceId):
    # Terminates an instance and decreases the desired number in its auto scaling group
    pass


def scale_in(cluster):
    # Iterates over hosts, finds the least utilized:
    #### top free memory -> lowest number of tasks
    # Drain the instance
    pass


def running_tasks(instance):
    # Return a number of running tasks on a given ECS host
    pass


def drain_instance(instance):
    # Put a given ec2 into draining state 
    pass


def future_reservation(cluster):
    # return cluster_mem_reserve*num_of_ec2 / num_of_ec2-1
    pass


def main():
    ecsClient = boto3.client('ecs')
    cwClient = boto3.client('cloudwatch')
    asgClient = boto3.client('autoscaling')
    for cluster in clusters(ecsClient):
        if empty_instances(cluster):
            for instance in empty_instances(cluster):
                drain_instance(instance)

        if draining_instances(cluster): 
            for instance in draining_instances(cluster):
                if not running_tasks(instance):
                    terminate_decrease(instance)

        if (future_reservation(cluster) < FUTURE_MEM_TH): 
            if (cluster_memory_reservation(cluster) < SCALE_IN_MEM_TH): 
                if (ec2_avg_cpu_utilization(cluster) < SCALE_IN_CPU_TH):
                # Cluster hosts can be scaled in
                    scale_in(cluster)            


if __name__ == '__main__':
    #main()
    #clusters(boto3.client('ecs'))
    #cluster_memory_reservation(boto3.client('cloudwatch'))

    ec2_avg_cpu_utilization('prod-machine', boto3.client('autoscaling'))








