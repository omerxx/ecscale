import boto3
import datetime
from optparse import OptionParser
import os

SCALE_IN_CPU_TH = 30
SCALE_IN_MEM_TH = 60
FUTURE_MEM_TH = 70
DRAIN_ALL_EMPTY_INSTANCES = True
ASG_PREFIX = ''
ASG_SUFFIX = ''
ECS_AVOID_STR = 'awseb'
logline = {}

def clusters(ecsClient):
    # Returns an iterable list of cluster names
    response = ecsClient.list_clusters()
    if not response['clusterArns']:
        print 'No ECS cluster found'
        return 

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

    except Exception:
        logger({'ClusterMemoryError': 'Could not retrieve mem reservation for {}'.format(clusterName)})


def find_asg(clusterName, asgData):
    # Returns auto scaling group resourceId based on name
    for asg in asgData['AutoScalingGroups']:
        for tag in asg['Tags']:
            if tag['Key'] == 'Name':
                if tag['Value'].split(' ')[0] == '{}{}{}'.format(ASG_PREFIX, clusterName, ASG_SUFFIX):
                    return tag['ResourceId']

    else:
        logger({'ASGError': 'Auto scaling group for {} not found'.format(clusterName)})


def ec2_avg_cpu_utilization(clusterName, asgData, cwclient):
    asg = find_asg(clusterName, asgData)
    response = cwclient.get_metric_statistics( 
        Namespace='AWS/EC2',
        MetricName='CPUUtilization',
        Dimensions=[
            {
                'Name': 'AutoScalingGroupName',
                'Value': asg
            },
        ],
        StartTime=datetime.datetime.utcnow() - datetime.timedelta(seconds=120),
        EndTime=datetime.datetime.utcnow(),
        Period=60,
        Statistics=['Average']
    )
    return response['Datapoints'][0]['Average']


def asg_on_min_state(clusterName, asgData, asgClient, activeInstanceCount):
    asg = find_asg(clusterName, asgData)
    for sg in asgData['AutoScalingGroups']:
        if sg['AutoScalingGroupName'] == asg:
            if activeInstanceCount <= sg['MinSize']:
                return True
    
    return False 


def empty_instances(clusterArn, activeContainerDescribed):
    # returns a object of empty instances in cluster
    instances = []
    empty_instances = {}

    for inst in activeContainerDescribed['containerInstances']:
        if inst['runningTasksCount'] == 0 and inst['pendingTasksCount'] == 0:
            empty_instances.update({inst['ec2InstanceId']: inst['containerInstanceArn']})

    return empty_instances


def draining_instances(clusterArn, drainingContainerDescribed):
    # returns an object of draining instances in cluster
    instances = []
    draining_instances = {} 

    for inst in drainingContainerDescribed['containerInstances']:
        draining_instances.update({inst['ec2InstanceId']: inst['containerInstanceArn']})

    return draining_instances


def terminate_decrease(instanceId, asgClient):
    # terminates an instance and decreases the desired number in its auto scaling group
    # [ only if desired > minimum ]
    try:
        response = asgClient.terminate_instance_in_auto_scaling_group(
            InstanceId=instanceId,
            ShouldDecrementDesiredCapacity=True
        )
        logger({'Action': 'Terminate', 'Message': response['Activity']['Cause']})

    except Exception as e:
        logger({'Error': e})


def scale_in_instance(clusterArn, activeContainerDescribed):
    # iterates over hosts, finds the least utilized:
    # The most under-utilized memory and minimum running tasks
    # return instance obj {instanceId, runningInstances, containerinstanceArn}
    instanceToScale = {'id': '', 'running': 0, 'freemem': 0}
    for inst in activeContainerDescribed['containerInstances']:
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

    logger({'Scale candidate': '{} with free {}'.format(instanceToScale['id'], instanceToScale['freemem'])})
    return instanceToScale

    
def running_tasks(instanceId, containerDescribed):
    # return a number of running tasks on a given ecs host
    for inst in containerDescribed['containerInstances']:
        if inst['ec2InstanceId'] == instanceId:
            return int(inst['runningTasksCount']) + int(inst['pendingTasksCount']) 
    

def drain_instance(containerInstanceId, ecsClient, clusterArn):
    # put a given ec2 into draining state
    try:
        response = ecsClient.update_container_instances_state(
            cluster=clusterArn,
            containerInstances=[containerInstanceId],
            status='DRAINING'
        )

    except Exception as e:
        logger({'DrainingError': e})


def future_reservation(activeInstanceCount, clusterMemReservation):
    # If the cluster were to scale in an instance, calculate the effect on mem reservation
    # return cluster_mem_reserve*active_instance_count / active_instance_count-1
    if activeInstanceCount > 1:
        futureMem = (clusterMemReservation*activeInstanceCount) / (activeInstanceCount-1)
    else:
        return 100

    print '*** Current: {} | Future : {}'.format(clusterMemReservation, futureMem)

    return futureMem


def retrieve_cluster_data(ecsClient, cwClient, asgClient, cluster):
    clusterName = cluster.split('/')[1]
    print '*** {} ***'.format(clusterName)
    activeContainerInstances = ecsClient.list_container_instances(cluster=cluster, status='ACTIVE')
    clusterMemReservation = cluster_memory_reservation(cwClient, clusterName)
    
    if activeContainerInstances['containerInstanceArns']:
        activeContainerDescribed = ecsClient.describe_container_instances(cluster=cluster, containerInstances=activeContainerInstances['containerInstanceArns'])
    else: 
        print 'No active instances in cluster'
        return False 
    drainingContainerInstances = ecsClient.list_container_instances(cluster=cluster, status='DRAINING')
    if drainingContainerInstances['containerInstanceArns']: 
        drainingContainerDescribed = ecsClient.describe_container_instances(cluster=cluster, containerInstances=drainingContainerInstances['containerInstanceArns'])
        drainingInstances = draining_instances(cluster, drainingContainerDescribed)
    else:
        drainingInstances = {}
        drainingContainerDescribed = [] 
    emptyInstances = empty_instances(cluster, activeContainerDescribed)

    dataObj = { 
        'clusterName': clusterName,
        'clusterMemReservation': clusterMemReservation,
        'activeContainerDescribed': activeContainerDescribed,
        'drainingInstances': drainingInstances,
        'emptyInstances': emptyInstances,
        'drainingContainerDescribed': drainingContainerDescribed        
    }

    return dataObj


def logger(entry, action='log'):
# print log as one-line json from cloudwatch integration
    if action == 'log':
        global logline
        logline.update(entry)
    elif action == 'print':
        print logline 
     

def main(run='normal'):
    ecsClient = boto3.client('ecs')
    cwClient = boto3.client('cloudwatch')
    asgClient = boto3.client('autoscaling')
    asgData = asgClient.describe_auto_scaling_groups()
    clusterList = clusters(ecsClient)

    for cluster in clusterList:
        ########### Cluster data retrival ##########
        clusterData = retrieve_cluster_data(ecsClient, cwClient, asgClient, cluster)
        if not clusterData:
            continue
        else:
            clusterName = clusterData['clusterName']
            clusterMemReservation = clusterData['clusterMemReservation']
            activeContainerDescribed = clusterData['activeContainerDescribed']
            activeInstanceCount = len(activeContainerDescribed['containerInstances'])
            drainingInstances = clusterData['drainingInstances']
            emptyInstances = clusterData['emptyInstances']
        ########## Cluster scaling rules ###########
        
        if drainingInstances.keys():
        # There are draining instances to terminate
            for instanceId, containerInstId in drainingInstances.iteritems():
                if not running_tasks(instanceId, clusterData['drainingContainerDescribed']):
                    if run == 'dry':
                        print 'Would have terminated {}'.format(instanceId)
                    else:
                        print 'Terminating draining instance with no containers {}'.format(instanceId)
                        terminate_decrease(instanceId, asgClient)
                else:
                    print 'Draining instance not empty'

        if asg_on_min_state(clusterName, asgData, asgClient, activeInstanceCount):
            print '{}: in Minimum state, skipping'.format(clusterName) 
            continue

        if (clusterMemReservation < FUTURE_MEM_TH and 
           future_reservation(activeInstanceCount, clusterMemReservation) < FUTURE_MEM_TH):
        # Future memory levels allow scale
            if DRAIN_ALL_EMPTY_INSTANCES and emptyInstances.keys():
            # There are empty instances                
                for instanceId, containerInstId in emptyInstances.iteritems():
                    if run == 'dry':
                        print 'Would have drained {}'.format(instanceId)  
                    else:
                        print 'Draining empty instance {}'.format(instanceId)
                        drain_instance(containerInstId, ecsClient, cluster)

            if (clusterMemReservation < SCALE_IN_MEM_TH):
            # Cluster mem reservation level requires scale
                if (ec2_avg_cpu_utilization(clusterName, asgData, cwClient) < SCALE_IN_CPU_TH):
                    instanceToScale = scale_in_instance(cluster, activeContainerDescribed)['containerInstanceArn']
                    if run == 'dry':
                        print 'Would have scaled {}'.format(instanceToScale)  
                    else:
                        print 'Draining least utilized instanced {}'.format(instanceToScale)
                        drain_instance(instanceToScale, ecsClient, cluster)
                else:
                    print 'CPU higher than TH, cannot scale'

        print '***'

def lambda_handler(event, context):
    parser = OptionParser()
    parser.add_option("-a", "--access-key", dest="AWS_ACCESS_KEY_ID", help="Provide AWS access key")
    parser.add_option("-s", "--secret-key", dest="AWS_SECRET_ACCESS_KEY", help="Provide AWS secret key")
    parser.add_option("-d", "--dry-run", action="store_true", dest="DRY_RUN", default=False, help="Dry run the process")
    (options, args) = parser.parse_args()

    if options.AWS_ACCESS_KEY_ID and options.AWS_SECRET_ACCESS_KEY:
        os.environ['AWS_ACCESS_KEY_ID'] = options.AWS_ACCESS_KEY_ID
        os.environ['AWS_SECRET_ACCESS_KEY'] = options.AWS_SECRET_ACCESS_KEY
    elif options.AWS_ACCESS_KEY_ID or options.AWS_SECRET_ACCESS_KEY:
        print 'AWS key or secret are missing'

    runType = 'dry' if options.DRY_RUN else 'normal'
    main(run=runType)


if __name__ == '__main__':
    # lambda_handler({}, '') 
    main()
    
