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

# debug
class debug ( object ) :
    def __init__ ( self ) :
        self.enabled = 0

        return

    def log ( self, data ) :
        if self.enabled:
            self.logfile.write(data + '\n')
            print(data)

        return

    def close ( self ) :
        self.logfile.close()

        return

    def enable ( self, debugfile ) :
        self.enabled = 1
        if os.path.exists(debugfile):
            self.logfile = open(debugfile, 'a')
        else:
            self.logfile = open(debugfile, 'w')

        self.log('<debug mode>')
        self.log(':: time: ' + datetime.datetime.now().isoformat())
        self.log(':: sys: ' + sys.version.replace('\n', '\n        '))
        self.log('</debug mode>')

        return

    def disable ( self ) :
        self.enabled = 0

        return

# ssh
class ssh ( object ) :

    def __init__ ( self ) :
        self.client = paramiko.SSHClient()
        self.ssh_config = paramiko.SSHConfig()
        self.user_config_file = os.path.expanduser('~/.ssh/config')
        if os.path.exists(self.user_config_file):
            with open(self.user_config_file) as f:
                self.ssh_config.parse(f)
        self.localpath = powercisco.devicepath
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

        ret = {'args':powercisco.args, 
               'user_config_file':self.user_config_file,
               'ssh_config':host,
               'login_output':out
              }

        return ret

    # TODO: support SSH and saving config
    # TODO: add download validation
    def download ( self, device, filename ) :
        localpath = powercisco.devicepath + device['host']
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

# handler
class powercisco ( object ) :

    def __init__ ( self ) :
        self.name = 'powercisco'
        self.version = '0.2'
        self.filename = os.path.basename(__file__)
        self.path = os.path.realpath(__file__).replace(self.filename,'')
        self.cfg = {
                     'debug_file':self.path + self.name + '.debug',
                     'device_path':self.path + 'devices/',
                     'ssh_config':'~/.ssh/config'
                   }
        self.dev = []
        self.dev_config = []
        self.dev_group = []
        self.dev_list = []

        self.configfile = self.path + self.name + '.json'
        self.debugfile = self.path + self.name + '.debug'
        self.devicepath = self.path + 'devices/'
        self.sshconfig = '~/.ssh/config'

        # create directories
        if not os.path.exists(self.devicepath):
            os.makedirs(self.devicepath)

        # handle arguments
        self.args = self.arguments()

        # enable stdout logging
        if self.args.log and self.args.log != '-':
            sys.stdout = open(self.args.log, 'w')
    
        # print banner
        print('=> ' + self.name + ' v' + self.version)

        # handle debug
        dbug = debug()
        if self.args.debug:
            dbug.enable(self.debugfile)

    # argument handler
    def arguments ( self ) :
        # TODO: add ssh key support
        parser = argparse.ArgumentParser(
                            description=self.name + 
                            ' v' + self.version + 
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
        
        if len(sys.argv) == 1:
            parser.print_help()
            sys.exit(1)
        
        args = parser.parse_args()
        
        return args

    # handler
    # TODO: error is now an array. need to handle accordingly
    def handler ( self ) :
        print(self.config('new', self.configfile))
        print(self.config('load', self.configfile))
        print(self.devices())

        output = {}
        devices = self.devices()
        for device in devices:
            print('>> device: ' + device['host'])
            output[device['host']] = {}

            # no auth required
            #if 'error' in device:
            #    print(':: error: ' + str(device['error']) + '. skipping.')
            #    continue
            #elif self.args.s:
            #    output[device['host']]['show'] = config_show(device, self.args.s)
            #    print(output[device['host']]['show'])

            # auth required
            creds = self.auth(device)
            device.update(creds)
            #if 'error' in device:
            #    print(':: error: ' + str(device['error']) + '. skipping.')
            #    continue
            if self.args.r:
                output[device['host']]['run'] = run_commands(device, self.args.r)
            elif self.args.d:
                output[device['host']]['download'] = config_download(device, self.args.d)

        return

    def config (self, action, filename ) :
        ret = {}
        if 'load' in action:
            try:
                config_load = json.loads(open(filename).read())
                if 'config' in config_load:
                    self.cfg.update(config_load['config'])
                if 'devices' in config_load:
                    self.dev_config = config_load['devices']
            except:
                ret = {'error':'failed to load configuration'}

        elif 'new' in action:
            try:
                data = {'config':{
                         'debug_file':self.path + self.name + '.debug',
                         'device_path':self.path + 'devices/',
                         'ssh_config':'~/.ssh/config'
                        },'devices':[
                          {'host':'device1','user':'','pass':'','groups':['dc1','cisco'],'compliance':['all']},
                          {'host':'device2','user':'','pass':'','groups':['dc2','cisco'],'compliance':['all']}
                        ]}

                with open(filename, 'w') as outfile:
                    json.dump(data, outfile, sort_keys=True, indent=2, separators=(',', ': '))
            except:
                ret = {'error':'failed to create configuration'}

        return ret

    def auth ( self, device ) :
        # TODO: return {'user':'','pass':'','error':''}
        # TODO: user order - cli, json, sshconfig 
        # TODO: pass order - cli, json
        # TODO: support ssh key
        ssh_config = paramiko.SSHConfig()
        user_config_file = os.path.expanduser(self.sshconfig)
        if os.path.exists(user_config_file):
            with open(user_config_file) as f:
                ssh_config.parse(f)

        host = ssh_config.lookup(device['host'])

        ret = { 'user':'', 'pass':'', 'error':[] }
        if self.args.u:
            ret['user'] = self.args.u[0]
        elif 'user' in host:
            ret['user'] = host['user']
        else:
            ret['error'].append('missing username')

        if self.args.p:
            ret['pass'] = self.args.p[0]
        else:
            ret['error'].append('missing password or key')

        return ret

    def devices ( self ) :
        # TODO: return {'host'}
        # TODO: combine devices - cli, json
        # TODO: handle duplicates
        ret = {}

        # list is always added
        if self.args.devices:
            for device in self.args.devices:
               self.dev_list.append({'host':device})
            self.dev = self.dev_list

        # group requires config
        # group is more grainular than config
        if self.args.groups:
            for group in self.args.groups:
                for device in self.dev_config:
                    if group in device['groups']:
                        self.dev_group.append(device)
            self.dev += self.dev_group
        elif self.dev_config:
            self.dev += self.dev_config

        ret = self.dev

        return ret

#### functions ####
# TODO: merge all functions under powercisco class

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
    localpath = powercisco.devicepath + device['host']
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

    localfile = powercisco.devicepath + device['host'] + '/' + config
    ret = None

    if not os.path.exists(localfile):
        print(':: error: ' + config + ' does not exist')

    sfile = open(localfile, 'r')
    ret = sfile.read()
    sfile.close()

    return ret

powercisco = powercisco()
powercisco.handler()
