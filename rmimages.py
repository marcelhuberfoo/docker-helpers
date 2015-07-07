from docker import Client
import pprint

# timeout in seconds
cli = Client(base_url='unix://var/run/docker.sock', timeout=120)
#cli.containers()

for c in cli.containers(filters={'status':'exited'}):
    name=c.get('Name')
    id=c.get('Id')
    print "removing container [{name}] [{Id}]".format(name=name, Id=id)
    # v=False to not accidentally remove host-volumes
    cli.remove_container(container=id,v=False)

for i in cli.images(filters={'dangling':True}):
    id=i.get('Id')
    print "removing dangling image [{Id}]".format(Id=id)
#    pprint.pprint(i)
    cli.remove_image(image=id)
