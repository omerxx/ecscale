# EC*SCALE*
### A serverless app removing underutilized hosts from ECS clusters

#### Scaling ECS down is not a straightforward task;Based on one metric solely, an instance could be taken down causing 2 effects:
 1. Forcefully removing a host when a container is running will cut off active connections causing service downtime
 2. Removing an instance based on utilization / capacity metric may cause an endless loop of scale


#### To such an end, this tool will look for scaleable clusters based on multiple metrics
Once identified, the target is moved to "draining" state, where a new instance of the same task is raised on an available host. Once the new containers are ready, the draining instsnce will start draining connection from active tasks.
Once the draining process is complete, the instance will be terminated.


#### Usage:
1. Throw `ecscale.py` code to AWS Lambda providing relevant role to handle ECS and autoscaling (Instrcutions ahead) 
2. Set repeated run (recommended every 60 minutes using a cloudwatch events trigger for Lambda)
3. That's it... Your ECS hosts are being gracefully removed if needed. No metrics/alarms needed

#### Changable Parameters:
* SCALE_IN_CPU_TH = 30 `# Below this EC2 average metric scaling would take action`
* SCALE_IN_MEM_TH = 60 `# Below this cluster average metric scaling would take action`
* FUTURE_CPU_TH = 40 `# Below this future metric scaling would take action`
* FUTURE_MEM_TH = 70 `# Below this future metric scaling would take action`
* ECS_AVOID_STR = 'awseb' `# Use this to avoid clusters containing a specific string (i.e ElasticBeanstalk clusters)`

##### How to create a role to run ecscale:
1. When creating the Lambda function, you'll be asked to select a role or create a new one, choose a new role
2. Provide the json from `policy.json` to the role policy
3. All set to allow ecscale to do its work

##### Creating a Lambda function step by step:

#### Flow logic
* Iterate over existing ECS clusters
* Check a cluster's ability to scale-in based on predicted future cpu and memory reservation capacity
* Look for empty hosts the can be scaled
* Look for least utilized host
* Choose a candidate and put in draining state
* Terminate a draining host that has no running tasks and decrease the desired number of instances

[Read about it some more on Medium](https://medium.com/@omerxx/how-to-scale-in-ecs-hosts-2d0906d2ba)
