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
containerdeps = {}
imagenamemap = {}

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
        portmap.append('--publish {hostip}{hostport}:{port}'.format(port=portonly, hostip=hostip, hostport=hostport))
    return portmap

def create_container_links(using_container, hostlinks):
    import os.path
    if not hostlinks:
        return []
    hostlinkslist=[]
    for linkentry in hostlinks:
        (container_raw, alias_raw)=linkentry.split(':')
        container = os.path.basename(container_raw)
        alias = os.path.basename(alias_raw)
        hostlinkslist.append('--link '+container+':'+alias)
        add_container_dep(using_container, container)
    return hostlinkslist

def create_env_list(envvalues):
    return ['--env "'+value+'"' for value in envvalues] if envvalues else []

def create_container_command(name, imagename, volumesfrom, startcommand=[], portbindings={}, configenv=[], hostlinks=[], stillToBindVolumes=[]):
    return create_format_string_list(['docker create', '--name {name}']+create_bind_volume_list(stillToBindVolumes)+volumes_from_list(volumesfrom)+create_env_list(configenv)+create_portbind_list(portbindings)+create_container_links(name, hostlinks)+['{imagename}', '{startcommand}'], name=name,imagename=imagename,startcommand=' '.join(startcommand))

def data_volume_create_container_command(name, imagename, datavolname):
    return create_format_string_list(['docker create', '--name {volfrom}', '--net none', '--entrypoint /bin/echo', '{imagename}', 'Data-only container for {name}'], name=name, imagename=imagename, volfrom=datavolname)

def container_uses_default_command(startargs, imagecmd):
    # startargs is either equal to imagecmd or equal to imagecmd without element at pos 0
    try:
        return imagecmd[imagecmd.index(startargs[0]):] == startargs
    except ValueError as e:
        return False
    except IndexError as e:
        return False

def create_container_exists_for_name(containerimport, newContainer):
    for item in containerimport:
        if isinstance(item, list) and isinstance(newContainer, list) and item[0:2] == newContainer[0:2]:
            return True
    return False

def add_container_dep(container, dependency):
    if not containerdeps.has_key(container) or not dependency in containerdeps.get(container):
        containerdeps.setdefault(container, []).append(dependency)

#for c in cli.containers(filters={'status':'running'}):
for c in cli.containers(all=True, filters={}):
    cid=c.get('Id')
    image_id=c.get('Image')
    ci=cli.inspect_container(cid)
    image_info=cli.inspect_image(image_id)
    name=ci.get('Name').lstrip('/')
    imagename=ci.get('Config').get('Image')
    startargs = ci.get('Args')
    imagecmd = image_info.get('Config').get('Cmd')
    configenv = ci.get('Config').get('Env')
    volumesfrom = ci.get('HostConfig').get('VolumesFrom')
    bindvolumes = ci.get('HostConfig').get('Binds')
    portbindings = ci.get('HostConfig').get('PortBindings')
    hostlinks = ci.get('HostConfig').get('Links')
    logger.debug(pprint.pformat(ci))
    containerimport = containersdict.setdefault(name, {}).setdefault('import', [])
    containerexport = containersdict.setdefault(name, {}).setdefault('export', [])
    containerexport[0:0]=["docker export {name} >{tarname}.export.tar".format(name=name, imagename=imagename, tarname=os.path.join(exportpath,name))]
    imagenamemap.setdefault(imagename, []).append(name)
    add_container_dep(name, imagename)
    if volumesfrom:
        vfrom=','.join(volumesfrom)
        logger.info("container [{name}] (id:{Id}) has volumes from [{vfrom}]".format(name=name, Id=cid[0:10], vfrom=vfrom))
        for datavolname in volumesfrom:
            volumestobackup=[]
            for volname,volpath in volumesinfo(datavolname).items():
                volumestobackup.append(volname)
                logger.info( "   volume [{volname}] with path [{volpath}]".format(volname=volname, volpath=volpath))
            dvimport = containersdict.setdefault(datavolname, {}).setdefault('import', [])
            dvexport = containersdict.setdefault(datavolname, {}).setdefault('export', [])
            dvimport.append(data_volume_create_container_command(name,imagename,datavolname))
            dvexport.append(data_volume_tar_command(datavolname, imagename, volumestobackup))
            dvimport.append(data_volume_tar_command(datavolname, imagename, [], 'xf'))
            add_container_dep(name, datavolname)
            add_container_dep(datavolname, imagename)
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
            dvimport = containersdict.setdefault(datavolname, {}).setdefault('import', [])
            dvexport = containersdict.setdefault(datavolname, {}).setdefault('export', [])
            dvimport.append(data_volume_create_container_command(name,imagename,datavolname))
            dvexport.append(bind_volume_tar_command(datavolname, hostvolume, localvolume, imagename, [localvolume]))
            dvimport.append(bind_volume_tar_command(datavolname, None, localvolume, imagename, [], 'xf'))
            add_container_dep(name, datavolname)
            add_container_dep(datavolname, imagename)
    newContainer=create_container_command(name, imagename, volumesfrom, startargs if not container_uses_default_command(startargs, imagecmd) else [], portbindings, configenv, hostlinks, stillToBindVolumes)
    if not create_container_exists_for_name(containerimport, newContainer):
        containerimport.append(newContainer)

def printItemOrList(item):
    if isinstance(item, list):
        print(' \\\n\t'.join(item))
    else:
        print(item)

logger.debug('Map of images to containers\n'+pprint.pformat(imagenamemap))
logger.info('Container dependencies\n'+pprint.pformat(containerdeps))

def get_imex_lines(imagename):
    firstcontainername = imagenamemap.get(imagename, [])[0]
    imex_dict={}
    containerimport = imex_dict.setdefault('import', [])
    containerexport = imex_dict.setdefault('export', [])
    tarimagefilename = os.path.join(exportpath,firstcontainername)+'.image'
    containerexport[0:0]=["docker save {imagename} >{tarname}.tar".format(name=firstcontainername, imagename=imagename, tarname=tarimagefilename)]
    containerimport[0:0]=["docker load <{tarname}.tar".format(name=firstcontainername,tarname=tarimagefilename)]
    return imex_dict
    
def print_imex_items(imex):
    for item in imex:
        printItemOrList(item)

def print_toposorted_export_import(name, containersdone, print_export=True, print_import=True):
    if not name or name in containersdone:
        return 
    logger.info('current item [{0}]'.format(name))
    for depend in containerdeps.get(name, []):
        print_toposorted_export_import(depend, containersdone, print_export, print_import)
    containersdone.append(name)
    imex = containersdict.get(name)
    label_prefix=''
    if not imex:
        # name is an image, create commands on the fly
        imex = get_imex_lines(name)
        label_prefix='Image '
    if print_export:
        print('\n{:#^80}'.format(' {count:>2}: {name} {label} '.format(name=name, count=len(containersdone), label=label_prefix+'Export')))
        print_imex_items(imex.get('export', []))
    if print_import:
        print('\n{:#^80}'.format(' {count:>2}: {name} {label} '.format(name=name, count=len(containersdone), label=label_prefix+'Import')))
        print_imex_items(imex.get('import', []))

containerdone=[]
for name in containerdeps.keys():
    print_toposorted_export_import(name, containerdone, True, False)

containerdone=[]
for name in containerdeps.keys():
    print_toposorted_export_import(name, containerdone, False, True)

