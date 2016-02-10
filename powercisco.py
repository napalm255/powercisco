#!/usr/bin/env python3.4

# imports
import argparse
import fileinput
import sys
import json
import os
import paramiko
import time
import datetime
from ciscoconfparse import CiscoConfParse

# application information
class app ( object ) :
    def __init__ ( self ) :
        self.name = 'powercisco'
        self.version = '0.1'
        self.filename = os.path.basename(__file__)
        self.path = os.path.realpath(__file__).replace(self.filename,'')
        self.debugfile = self.path + self.name + '.debug'
        self.devicepath = self.path + 'devices/'
        if not os.path.exists(self.devicepath):
            os.makedirs(self.devicepath)

        return

class debug ( object ) :
    def __init__ ( self, app = app() ) :
        self.enabled = 0
        print('=> ' + app.name + ' v' + app.version)

        return

    def log ( self, data ) :
        if self.enabled:
            self.logfile.write(data + '\n')
            print(data)

        return

    def close ( self ) :
        self.logfile.close()

        return

    def enable ( self ) :
        self.enabled = 1
        if os.path.exists(app.debugfile):
            self.logfile = open(app.debugfile, 'a')
            self.log(':: debug mode enabled')
            self.log(':: debug log already exists')
            self.log(':: time: ' + datetime.datetime.now().isoformat())
            self.log(':: sys: ' + sys.version.replace('\n', '\n        '))
        else:
            self.logfile = open(app.debugfile, 'w')
            self.log(':: debug log does not exist')

        return

    def disable ( self ) :
        self.enabled = 0

        return

# config handler
class config ( object ) :
    data = {}

    def __init__ ( self ) :
        return

    def load ( self, filename ) :
        self.data.update(json.loads(open(filename).read()))

        return self.data

    def new ( self, type, filename ) :
        if 'app' in type :
            data = {'config':[
                     {'device_path':'/devices'}
                   ]}
        elif 'dev' in type :
            data = {'devices':[
                     {'host':'device1','user':'','pass':'','groups':['dc1','cisco'],'compliance':['all']},
                     {'host':'device2','user':'','pass':'','groups':['dc2','cisco'],'compliance':['all']}
                   ]}

        with open(filename, 'w') as outfile:
            json.dump(data, outfile, sort_keys=True, indent=2, separators=(',', ': '))

        return

# ssh handler
class ssh ( object ) :

    def __init__ ( self ) :
        self.client = paramiko.SSHClient()
        self.ssh_config = paramiko.SSHConfig()
        self.user_config_file = os.path.expanduser('~/.ssh/config')
        if os.path.exists(self.user_config_file):
            with open(self.user_config_file) as f:
                self.ssh_config.parse(f)
        self.localpath = app.devicepath
        if not os.path.exists(self.localpath):
            os.makedirs(self.localpath)


        return

    def close ( self ) :
        if self.client:
            self.client.close()

        return

    def connect ( self, device ) :
        host = self.ssh_config.lookup(device['host'])

        self.client.load_system_host_keys()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            self.client.connect(device['host'], username=device['user'], password=device['pass'], timeout=10)
        except:
            return {'error':'failed to connect'}

        try:
            self.channel = self.client.invoke_shell()
        except:
            return {'error':'failed to initiate channel'}

        while not self.channel.recv_ready():
            time.sleep(.25)
        out = ''
        while self.channel.recv_ready():
            out = out + str(self.channel.recv(1024))

        ret = {'args':args, 
               'user_config_file':self.user_config_file,
               'ssh_config':host,
               'login_output':out
              }

        return ret

    # TODO: support SSH and saving config
    # TODO: add download validation
    def download ( self, device, filename ) :
        localpath = app.devicepath + device['host']
        if not os.path.exists(localpath):
            os.makedirs(localpath)

        try:
            self.sftp = self.client.open_sftp()
            ret = self.sftp.get(filename, localpath + '/' + filename)
            self.sftp.close()
        except:
            ret = { 'error':'failed to download file' }

        return ret

    def run ( self, cmds ) :
        if not self.channel:
            return {'error':'channel not open'}

        ret = []
        for cmd in cmds:
            self.channel.send(cmd + '\n')
            while not self.channel.recv_ready():
                time.sleep(.25)
            out = ''
            while self.channel.recv_ready():
                out = out + str(self.channel.recv(1024))
            ret.append({'command':cmd, 'output':out})

        self.channel.send('exit\n')

        return ret

#### functions ####

# authentication handler
#    lookup/combine credentials from different sources
# TODO: support key
def handler_auth ( device ) :
    ssh_config = paramiko.SSHConfig()
    user_config_file = os.path.expanduser('~/.ssh/config')
    if os.path.exists(user_config_file):
        with open(user_config_file) as f:
            ssh_config.parse(f)

    host = ssh_config.lookup(device['host'])

    ret = { 'user':'', 'pass':'' }
    if args.u:
        ret['user'] = args.u[0]
    elif 'user' in host:
        ret['user'] = host['user']
    else:
        msg = 'missing username'
        if 'error' in ret:
            ret['error'] = ret['error'] + '; ' + msg
        else:
            ret['error'] = msg

    if args.p:
        ret['pass'] = args.p[0]
    else:
        msg = 'missing password or key'
        if 'error' in ret:
            ret['error'] = ret['error'] + '; ' + msg
        else:
            ret['error'] = msg

    return ret

# device handler
#    lookup/combine devices
def handler_devices ( ) :
    ret = ''
    # load device list
    if args.devices:
        print(':: loading device list')
        for device in args.devices:
            if not ret:
                ret = [{'host':device}]
            else:
                ret.append({'host':device})

    # load device configuration
    if args.config:
        if 'dev' in args.config:
            print(':: loading device config')
            cfg = config()
            cfg.load('dev.json')
            for device in cfg.data['devices']:
                if not ret:
                    ret = [device]
                else:
                    ret.append(device)

    # filter for groups
    # TODO: add actual filter
    if args.groups:
        print(':: filtering groups')
        print(args.groups)

    return ret

# handler
#   what to run and in what order
def handler ( ) :
    output = {}

    # enable stdout logging
    if args.log and args.log != '-':
        sys.stdout = open(args.log, 'w')
    
    # enable debugging
    if args.debug:
        debug.enable()
    
    # generate new config from template
    if args.new:
        # TODO:check if already exists
        newcfg = config()
        for cfg in args.new:
            print(':: generating new ' + cfg + ' config')
            newcfg.new(cfg, cfg + '.json')
        newcfg = None
        print(':: finished')
        return

    # loop through devices
    devices = handler_devices()
    for device in devices:
        print('>> device: ' + device['host'])
        output[device['host']] = {}

        if 'error' in device:
            print(':: error: ' + device['error'])
            print(':: skipping')
            continue

        if args.r:
            creds = handler_auth(device)
            device.update(creds)
            output[device['host']]['run'] = run_commands(device, args.r)

        if args.d:
            creds = handler_auth(device)
            device.update(creds)
            output[device['host']]['download'] = config_download(device, args.d)

        if args.s:
            output[device['host']]['show'] = config_show(device, args.s)
            print(output[device['host']]['show'])

    return output

# save file
def save_file ( filename, data ) :
    ret = {}
    try:
        sfile = open(filename, 'w')
        sfile.write(data)
        sfile.close()
    except:
        ret = {'error':'failed to save file'}

    return ret

# run commands
def run_commands ( device, cmds ) :
    print(':: running commands\n   ' + str(cmds))
    s = ssh()
    ret = {}
    ret = s.connect(device)
    if not 'error' in ret:
        ret = s.run(cmds)
    s.close()

    return ret

# download cisco configuration
def config_download ( device, configs ) :
    print(':: downloading configuration')
    localpath = app.devicepath + device['host']
    if not os.path.exists(localpath):
        os.makedirs(localpath)

    for config in configs:
        if 'run' in config: config = 'running-config'
        if 'start' in config: config = 'startup-config'
        if 'tech' in config: config = 'show-tech'
        s = ssh()
        ret = {}
        ret = s.connect(device)
        if not 'error' in ret:
            if 'show-tech' in config:
                ret = s.run(['show tech'])
                save_file(localpath + '/' + config, ret[0]['output'])
            else:
                ret = s.download(device, config)
        s.close()

    return ret

# show cisco configuration
def config_show ( device, config ) :
    print(':: showing configuration')

    if 'run' in config: config = 'running-config'
    if 'start' in config: config = 'startup-config'
    if 'tech' in config: config = 'show-tech'

    localfile = app.devicepath + device['host'] + '/' + config
    ret = None

    if not os.path.exists(localfile):
        print(':: error: ' + config + ' does not exist')

    sfile = open(localfile, 'r')
    ret = sfile.read()
    sfile.close()

    return ret

#### initialization ####

# load application information
app = app()
debug = debug()

# argument handler
# TODO: add key support
parser = argparse.ArgumentParser(
                    description=app.name + 
                    ' v' + app.version + 
                    ' - managing cisco devices',
                    prog='tool',
                    formatter_class=lambda prog:
                      argparse.HelpFormatter(prog,max_help_position=50)
                  )
parser.add_argument('-u', nargs=1,
                   help='username')
parser.add_argument('-p', nargs=1,
                   help='password')
#parser.add_argument('-k', nargs=1,
#                   help='ssh key file')
parser.add_argument('-r', nargs='+',
                   help='command(s) to run')
parser.add_argument('-d', nargs='+', choices=['run', 'start', 'tech'],
                   help='download cisco configuration(s)')
parser.add_argument('-c', nargs='+',
                   help='cisco configuration file(s)')
parser.add_argument('-s', choices=['run', 'start', 'tech'],
                   help='show cisco configuration(s)')
parser.add_argument('--devices', nargs='+',
                   help='device(s)')	
parser.add_argument('--groups', nargs='+',
                   help='group(s)')
parser.add_argument('--config', nargs='+', choices=['app', 'dev'],
                   help='load json config(s)')
parser.add_argument('--new', nargs='+', choices=['app', 'dev'],
                   help='new json config(s)')
parser.add_argument('--debug', action='store_true',
                   help='enable debug')
parser.add_argument('--out', nargs='?',
                   help='output to file')
parser.add_argument('--log', nargs='?',
                   default='-',
                   help='log to file')
args = parser.parse_args()

# handle it
ret = handler()
#if ret:
#    print(ret)
