from docker import Client
import pprint
import os
from logging import getLogger
from Logging import setup_logging

_base_path = os.path.dirname(__file__)
#sys.path[:0] = [_base_path]
setup_logging(os.path.join(_base_path, 'logging.yaml'))
logger = getLogger(__name__)

# timeout in seconds
cli = Client(base_url='unix://var/run/docker.sock', timeout=120)

exportpath=os.path.sep+'tmp'
containersdict = {}

def volumesinfo(container_id):
    ci=cli.inspect_container(container_id)
    volumes = ci.get('Volumes')
    return volumes

def format_string(string, **kw):
    return string.format(**kw)

def create_format_string_list(items, **kw):
    return [string for string in [format_string(item, **kw) for item in items] if string]

def volumes_from_list(volumes):
    return [format_string('--volumes-from {vol}', vol=vol) for vol in volumes] if volumes else []

def data_volume_tar_command(datavolname,imagename,backupvolumes,tarcreateextractoption='cf'):
    return create_format_string_list(['docker run --rm', '--volume {exportpath}']+volumes_from_list([datavolname])+['--entrypoint /bin/tar', '{imagename}', '{taroption} {tarfilename}.tar', '--absolute-names', '{backupvolumes}'], exportpath=exportpath+':'+exportpath,tarfilename=os.path.join(exportpath,datavolname),imagename=imagename,taroption=tarcreateextractoption,backupvolumes=' '.join(backupvolumes))

def create_bind_volume_list(bindvolumes):
    volumeslist=[]
    for (hostvol, localvol) in bindvolumes:
        if hostvol:
            volumeslist.append('--volume '+hostvol+':'+localvol)
    return volumeslist

def bind_volume_tar_command(datavolname, hostvolume, localvolume, imagename, backupvolumes, tarcreateextractoption='cf'):
    return create_format_string_list(['docker run --rm', '--volume {exportpath}']+create_bind_volume_list([(hostvolume, localvolume)])+volumes_from_list([datavolname] if not hostvolume else [])+['--entrypoint /bin/tar', '{imagename}', '{taroption} {tarfilename}.tar', '--absolute-names', '{backupvolumes}'], exportpath=exportpath+':'+exportpath, tarfilename=os.path.join(exportpath,datavolname),imagename=imagename,taroption=tarcreateextractoption, backupvolumes=' '.join(backupvolumes))

def create_portbind_list(portbindings):
    portmap=[]
    for (localport, hostmap) in portbindings.items():
        portonly=localport.split('/')[0]
        firstentry=hostmap[0]
        hostip=firstentry.get('HostIp', None)
        if hostip:
            hostip+=':'
        hostport=firstentry.get('HostPort', None)
        portmap.append('-p {hostip}{hostport}:{port}'.format(port=portonly, hostip=hostip, hostport=hostport))
    return portmap

def create_container_links(hostlinks):
    import os.path
    if not hostlinks:
        return []
    hostlinkslist=[]
    for linkentry in hostlinks:
        (container_raw, alias_raw)=linkentry.split(':')
        container = os.path.basename(container_raw)
        alias = os.path.basename(alias_raw)
        hostlinkslist.append('--link '+container+':'+alias)
    return hostlinkslist

def create_container_command(name, imagename, volumesfrom, startcommand=[], portbindings={}, configenv=[], hostlinks=[], stillToBindVolumes=[]):
    return create_format_string_list(['docker create', '--name {name}']+create_bind_volume_list(stillToBindVolumes)+volumes_from_list(volumesfrom)+['--env '+value for value in configenv]+create_portbind_list(portbindings)+create_container_links(hostlinks)+['{imagename}', '{startcommand}'], name=name,imagename=imagename,startcommand=' '.join(startcommand))

def data_volume_create_container_command(name, imagename, datavolname):
    return create_format_string_list(['docker create', '--name {volfrom}', '--net none', '--entrypoint /bin/echo', '{imagename}', 'Data-only container for {name}'], name=name, imagename=imagename, volfrom=datavolname)

def container_uses_default_command(startargs, configargs):
    # startargs is either equal to configargs or equal to configargs without element at pos 0
    return configargs[configargs.index(startargs[0]):] == startargs if len(startargs)>=1 else True

#for c in cli.containers(filters={'status':'running'}):
for c in cli.containers(all=True, filters={}):
    cid=c.get('Id')
    ci=cli.inspect_container(cid)
    name=ci.get('Name').lstrip('/')
    imagename=ci.get('Config').get('Image')
    startargs = ci.get('Args')
    configargs = ci.get('Config').get('Cmd')
    configenv = ci.get('Config').get('Env')
    volumesfrom = ci.get('HostConfig').get('VolumesFrom')
    bindvolumes = ci.get('HostConfig').get('Binds')
    portbindings = ci.get('HostConfig').get('PortBindings')
    hostlinks = ci.get('HostConfig').get('Links')
    logger.debug(pprint.pformat(ci))
    containersdict[name]={'export':[],'import':[]}
    containerimport = containersdict.get(name).get('import')
    containerexport = containersdict.get(name).get('export')
    containerexport.append("docker export {name} >{tarname}.export.tar".format(name=name, imagename=imagename, tarname=os.path.join(exportpath,name)))
    containerexport.append("docker save {imagename} >{tarname}.tar".format(name=name, imagename=imagename, tarname=os.path.join(exportpath,name)))
    containerimport.append("docker load <{tarname}.tar".format(name=name,tarname=os.path.join(exportpath,name)))
    if volumesfrom:
        vfrom=','.join(volumesfrom)
        logger.info("container [{name}] (id:{Id}) has volumes from [{vfrom}]".format(name=name, Id=cid[0:10], vfrom=vfrom))
        for datavolname in volumesfrom:
            volumestobackup=[]
            for volname,volpath in volumesinfo(datavolname).items():
                volumestobackup.append(volname)
                logger.info( "   volume [{volname}] with path [{volpath}]".format(volname=volname, volpath=volpath))
            containerimport.append(data_volume_create_container_command(name,imagename,datavolname))
            containerexport.append(data_volume_tar_command(datavolname, imagename, volumestobackup))
            containerimport.append(data_volume_tar_command(datavolname, imagename, [], 'xf'))
    stillToBindVolumes=[]
    if bindvolumes:
        bfrom=','.join(bindvolumes)
        logger.info("container [{name}] (id:{Id}) has bound volumes".format(name=name, Id=cid[0:10]))
        volumesfrom=[]
        for volmapping in bindvolumes:
            (hostvolume,localvolume)=volmapping.split(':')
            stillToBindVolumes.append((hostvolume,localvolume))
            # do not create data volume for docker.sock or X11-unix
            if hostvolume in [u'/var/run/docker.sock', '/tmp/.X11-unix']:
                continue
            logger.info( "   hostvolume [{volname}] localpath [{volpath}]".format(volname=hostvolume, volpath=localvolume))
            datavolname=name+'-data'
            volumesfrom.append(datavolname)
            containerimport.append(data_volume_create_container_command(name,imagename,datavolname))
            containerexport.append(bind_volume_tar_command(datavolname, hostvolume, localvolume, imagename, [localvolume]))
            containerimport.append(bind_volume_tar_command(datavolname, None, localvolume, imagename, [], 'xf'))
    containerimport.append(create_container_command(name, imagename, volumesfrom, startargs if not container_uses_default_command(startargs, configargs) else [], portbindings, configenv, hostlinks, stillToBindVolumes))

def printItemOrList(item):
    if isinstance(item, list):
        print(' \\\n\t'.join(item))
    else:
        print(item)

count=0
for (name, imex) in containersdict.items():
    print('{:#^50}'.format(' {count:>2}: {name} '.format(name=name, count=count)))
    print('#{:-^48}#'.format('Export'))
    for item in imex.get('export', []):
        printItemOrList(item)
    print('\n#{:-^48}#'.format('Import'))
    for item in imex.get('import', []):
        printItemOrList(item)
    print('#{:^48}#'.format(''))
    print('{:#^50}'.format(''))
    count+=1

