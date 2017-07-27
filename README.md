# ECS scaling-in

# Scaling ECS down is not a stragitforward task;
## Based on one metric solely, an instance could be taken down causing 2 effects:
 1. Forcefully removing a host when a container is running will cut off active connections
 2. Removing an instance based on utilization / capacity metric may cause an endless loop of scale

----

## To such an end, this tool will look for scaleable clusters based on multiple metrics.
Once identified, the target is moved to "draining" state, where a new instance of the same task is raised on an available host. Once the new containers are ready, the draining instsnce will start draining connection from active tasks.
Once the draining process is complete, the instance will be terminated.


## Configurable parameters

### Memory reservation levels (defaults to 55%)
The tool searches for clusters with a total memory reservation lower than 55%.
Note: Memory reservation is *not* memory utilization; it measures the actual memory "space" resrved for active containers, it only changes when a container is brought up or down, and can predict whether new container has "room" to operate in terms of virtual memory.

Note2: Having lower than 55% memory reservation is not a gurantee for scaleable clusters, one should optimize this level according to size of cluster, size of running containers, and the distribution of memory between tasks.


### CPU Utilization levels (defaults to 20%)
If the total levels of CPU utilization of all services running on the cluster is lower than this thershold, the cluster would be considered in-scaleable in terms of CPU.


### Cluster engagment
Determines whether the tool runs through all available ECS clusters in an account (`ENGAGE=all`),
or searches for a prefix (`ENGAGE=prefix`, `PREFIX=abc`),
or searches for a specific cluster (`ENGAGE=specific`, `CLUSTER=somename`)

