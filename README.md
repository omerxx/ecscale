# EC*S*CALE 
## A servresless app removing underutilized hosts from ECS clusters

### Scaling ECS down is not a straightforward task;Based on one metric solely, an instance could be taken down causing 2 effects:
 1. Forcefully removing a host when a container is running will cut off active connections causing service downtime
 2. Removing an instance based on utilization / capacity metric may cause an endless loop of scale


### To such an end, this tool will look for scaleable clusters based on multiple metrics
Once identified, the target is moved to "draining" state, where a new instance of the same task is raised on an available host. Once the new containers are ready, the draining instsnce will start draining connection from active tasks.
Once the draining process is complete, the instance will be terminated.


### Getting started:
1. Add `ecscale.py` to AWS Lambda providing relevant role to handle ECS and EC2
2. Set repeated run (recommended every 60 minutes as ec2 instances are paid hourly as it it)


### Flow logic
* Iterate over existing ECS cluster using AWS keys
* Check a cluster's ability to scale-in based on predicted future memory reservation capacity
* Look for empty hosts the can be scaled
* Look for least utilized host
* Choose a candidate and put in draining state
* Terminate a draining host that has no running tasks and decrease the desired number of instances