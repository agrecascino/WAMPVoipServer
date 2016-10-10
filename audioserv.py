import asyncio
from asyncio import coroutine
import rsa
import time
from autobahn.wamp.types import SubscribeOptions
from autobahn.asyncio.wamp import ApplicationSession, ApplicationRunner
import base64
class Channel:
    def __init__(self, name,session):
        self.name = name
        self.users = []
        self.session = session

    def publish(self,channel,args):
        self.session.publish(channel,args)
    def findUser(self,name):
        for username in self.users:
            if(username == name):
                return username
        return -1

    def addUser(self,name):
        self.broadcastToChannelUsers(name,['NEWCHANUSER',self.name,name])
        self.users.append(name)
        for username in self.users:
            user = self.session.findUser(username)
            if (user != -1):
                self.publish(user.ctlchan, user.name)


    def removeUser(self,name):
        rv = self.findUser(name)
        if(rv != -1):
            user = self.session.findUser(name)
            if(user != -1):
                user.channel = ""
            self.users.remove(name)
            self.broadcastToChannelUsers(name,['PRUNECHANUSER', self.name, name])
        else:
            return -1

    def broadcastToChannelUsers(self,name,args):
        for username in self.users:
            if (username != name):
                user = self.session.findUser(username)
                if (user != -1):
                    user.publish(user.ctlchan, args)
                else:
                    self.removeUser(username)

    def pushToChannelFromUser(self,name,message):
        obj = self.findUser(name)
        if ((obj != -1) and (message != '')):
            for username in self.users:
                if (username != obj):
                    user = self.session.findUser(username)
                    if(user != -1):
                        user.publish(user.ctlchan,[':','MESSAGE',user.name,self.name,message])
                    else:
                        self.removeUser(username)

    def __destructor__(self):
        for username in self.users:
            obj = self.session.findUser(username)
            if(obj != -1):
                obj.channel = ""



class User:
    def __init__(self, name, ctlchan, audiochan, session,pubkey):
        self.name = name
        self.ctlchan = ctlchan
        self.audiochan = audiochan
        self.session = session
        self.channel = ""
        self.role = "user"
        self.subscription = None
        self.systemtime = int(time.time())
        self.pubkey = rsa.PublicKey.load_pkcs1(base64.b64decode(pubkey),'DER')
        print("Making user with name " + self.name)
        print("Attaching channel " + self.ctlchan)
        self.publish(self.ctlchan,['~','PUBKEY',str(base64.b64encode(self.session.serverpubkey.save_pkcs1('DER')))])

    def publish(self, channel, arguments):
        print("publishing")
        encrypted_arguments = []
        if arguments[0] == '~':
           print("sneksnek")
           for i in range(len(arguments)):
               arguments[i] = str(arguments[i])
               print(arguments[i])
           self.session.publish(channel,arguments)
           print("snek")
           return
        for argument in arguments:
            print(argument)
            encrypted_arguments.append(str(base64.b64encode(rsa.encrypt(bytearray(argument,'utf-8'),self.pubkey)).decode('UTF-8')))
        for i in range(len(encrypted_arguments)):
            print(encrypted_arguments[i])
        self.session.publish(channel, encrypted_arguments)
        print("sent")

    def ctlCallback(self, *commands_tuple):
        print(commands_tuple[0])
        commands = []
        for i in range(len(commands_tuple)):
            commands.append((rsa.decrypt(base64.b64decode(commands_tuple[i]),self.session.serverprivkey)).decode("utf-8"))
        if (commands[0] == "PING"):
            self.systemtime = int(time.time())
            return
        print(commands[0])
        if (commands[0] == "JOINCHANNEL" and self.session.findChannel(commands[1]) != -1):
            self.channel = commands[1]
            self.session.findChannel(commands[1]).addUser(self.name)
            self.publish(self.ctlchan, [':', 'JOINCHANNEL', commands[1]])
            return
        elif(commands[0] == "JOINCHANNEL"):
            self.publish(self.ctlchan, [':', 'ERR', 'CHANNOTFOUND'])
            return
        if (commands[0] == "LEAVECHANNEL" and self.session.findChannel(commands[1]) != -1 and (self.channel == commands[1])):
            self.channel = ""
            self.session.findChannel(commands[1]).removeUser(self.name)
            self.publish(self.ctlchan, [':', 'LEAVECHANNEL', commands[1]])
            return
        if (commands[0] == "QUIT"):
            self.__destructor__()
            return
        elif(commands[0] == "LEAVECHANNEL"):
            self.publish(self.ctlchan, [':', 'ERR', 'CHANNOTFOUND'])
            return
        if (commands[0] == "MKCHANNEL") and (self.session.findChannel(commands[1]) == -1 and commands[1] != ""):
            print('Creating channel with name ' + commands[1])
            self.session.channelarr.append(Channel(commands[1],self.session))
            return
        elif(commands[0] == "MKCHANNEL"):
            self.publish(self.ctlchan, [':', 'ERR', 'CHANALREADYEXISTS'])
            return
        if (commands[0] == "RMCHANNEL") and (self.session.findChannel(commands[1]) != -1 and commands[1] != ""):
            print('Deleting channel with name ' + commands[1])
            obj = self.session.findChannel(commands[1])
            if(obj != -1):
                obj.__destructor__()
                self.session.removeChannel(obj)
            return
        elif(commands[0] == "RMCHANNEL"):
            self.publish(self.ctlchan,[':','ERR','CHANNOTFOUND'])
            return
        if (commands[0] == "MESSAGE") and (self.session.findChannel(commands[1]) != -1 and commands[1] != ""):
           self.session.findChannel(commands[1]).pushToChannelFromUser(user.name,commands[2])
           return
        if (commands[0] == "CHANNAMES"):
            for channel in self.session.channelarr:
                self.publish(self.ctlchan, [':', 'CHANNAME', channel.name])
            return
    def __destructor__(self):
        yield from self.subscription.unsubscribe()
        obj = self.session.findChannel(self.channel)
        if (obj != -1):
            obj.removeUser(self.name)


class Server(ApplicationSession):
    @asyncio.coroutine
    def pruneLoop(self):
        while True:
            self.pruneUsers()
            yield from asyncio.sleep(1)

    def findChannel(self,name):
        for channel in self.channelarr:
            if (channel.name == name):
                return channel
        return -1

    def findUser(self,name):
        for user in self.userarr:
            if (user.name == name):
                return user
        return -1

    def removeUser(self,user):
        if (self.findUser(user.name) == -1):
            return -1
        self.userarr.remove(user)

    def removeChannel(self,channel):
        if (self.findChannel(channel.name) == -1):
            return -1
        self.channelarr.remove(channel)

    def removeUserFromName(self,name):
        obj = self.findUser(name)
        if (obj != -1):
            self.userarr.remove(obj)
        else:
            return -1

    def removeChannelFromName(self,name):
        obj = self.findChannel(name)
        if (obj != -1):
            self.channelarr.remove(obj)
        else:
            return -1

    def pruneUsers(self):
        for user in self.userarr:
            if((int(time.time() - user.systemtime)) > 5):
                user.__destructor__()
                self.removeUser(user)

    def onMainCtlEvent(self, *command):
        if(command[0] == "NICK" and (self.findUser(command[1])) == -1):
            user = User(command[1], 'com.audioctl.' + command[1], 'com.audiodata.' + command[1], self,command[2])
            self.userarr.append(user)
            user.subscription = yield from self.subscribe(user.ctlCallback, user.ctlchan)

    def onJoin(self, details):
        self.initialize()
        yield from self.subscribe(self.onMainCtlEvent, u"com.audioctl.main")
        yield from self.pruneLoop()

    def initialize(self):
        self.userarr = []
        self.channelarr = []
        (self.serverpubkey, self.serverprivkey) = rsa.newkeys(1536)


runner = ApplicationRunner(u"ws://127.0.0.1:8080/ws", u"realm1")
runner.run(Server)
