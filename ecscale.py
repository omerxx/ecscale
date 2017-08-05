#!/bin/python
import boto3

SCALE_IN_CPU_TH=30
SCALE_IN_MEM_TH=60


def clusters():
    # Returns an iterable list of cluster names
    pass()


def cluster_memory_reservation():
    pass()


def ec2_avg_cpu_utilization():
    pass()


def empty_instances(cluster):
    # Returns a list of empty instances in cluster
    pass()


def draining_instances(cluster):
    # Returns a list of draining instances in cluster
    pass()


def terminate_decrease(instanceId):
    # Terminates an instance and decreases the desired number in its auto scaling group
    pass()


def scale_in(cluster):
    # Iterates over hosts, finds the least utilized:
    #### top free memory -> lowest number of tasks
    # Drain the instance


def running_tasks(instance):
    # Return a number of running tasks on a given ECS host
    pass()


def drain_instance(instance):
    # Put a given ec2 into draining state 
    pass()


def main():
    for cluster in clusters():
        if empty_instances(cluster):
            for instance in empty_instances(cluster):
                drain_instance(instance)

        if draining_instances(cluster):
            for instance in draining_instances(cluster):
                if not running_tasks(instance):
                    terminate_decrease(instance)

        if (cluster_memory_reservation(cluster) < 60) and (ec2_avg_cpu_utilization(cluster) < 30):
            # Cluster hosts can be scaled in
            scale_in(cluster)            


if __name__ == '__main__':
    main()

















