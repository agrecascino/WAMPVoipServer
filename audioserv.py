import asyncio
from asyncio import coroutine
import time
from autobahn.wamp.types import SubscribeOptions
from autobahn.asyncio.wamp import ApplicationSession, ApplicationRunner
import base64
import datetime

class Rule:
	def __init__(self,session,uri,action,allow):
		self.session = session
		self.uri = uri
		self.action = action
		self.allow = allow

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
        self.broadcastToChannelUsers(name,[':','NEWCHANUSER',self.name,name])
        self.users.append(name)
        listener = self.session.findUser(name)
        names = [':','CHANUSERNAMES',self.name]
        for username in self.users:
            user = self.session.findUser(username)
            if (user != -1):
                self.session.ruleModify([listener.userid,user.audiochan,'call',True,False])
                self.session.ruleModify([user.userid,listener.audiochan,'call',True,False])
                names.append(username)
        listener.publish(user.ctlchan, names)


    def removeUser(self,name):
        rv = self.findUser(name)
        if(rv != -1):
            user = self.session.findUser(name)
            if(user != -1):
                user.channel.remove(self.name)
                for username in self.users:
                    listener = self.session.findUser(username)
                    if (listener != 1):
                        self.session.ruleModify([user.userid,listener.audiochan,'call',True,True])
                        self.session.ruleModify([listener.userid,user.audiochan,'call',True,True])
            self.users.remove(name)
            self.broadcastToChannelUsers(name,[':','PRUNECHANUSER', self.name, name])
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
                        user.publish(user.ctlchan,[':','MESSAGE',name,self.name,message])
                    else:
                        self.removeUser(username)

    def __destructor__(self):
        for username in self.users:
            obj = self.session.findUser(username)
            if(obj != -1):
                self.removeUser(username)



class User:
    def __init__(self, name, ctlchan, audiochan, session, userid):
        self.name = name
        self.ctlchan = ctlchan
        self.audiochan = audiochan
        self.session = session
        self.channel = []
        self.role = "user"
        self.subscription = None
        self.systemtime = int(time.time())
        self.ft = True
        self.userid = userid
        self.dead = False
        self.session.ruleModify([self.userid,self.ctlchan,'publish',True,False])
        self.session.ruleModify([self.userid,self.ctlchan,'subscribe',True,False])
        print("Making user with name " + self.name)
        print("Attaching channel " + self.ctlchan)
        print("Time at object creation" + datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S:%f"))

    def publish(self, channel, arguments):
        print("publishing") 
        self.session.publish(channel,arguments)

    async def ctlCallback(self, *commands_tuple):
        commands = []
        for i in range(len(commands_tuple)):
            commands.append(commands_tuple[i])
        if (commands[0] == "PING"):
            if(self.ft):
                print("Time at entering ping block" + datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S:%f"))
                self.session.ruleModify([self.userid,self.audiochan,'register',True,False])
                self.publish(self.ctlchan,[':','HELLO','127.0.0.1'])
                self.ft = False
                print("Time at exiting ping block" + datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S:%f"))
            self.systemtime = int(time.time())
            return
        if (commands[0] == "JOINCHANNEL" and self.session.findChannel(commands[1]) != -1 and not (commands[1] in self.channel)):
            self.channel.append(commands[1])
            self.publish(self.ctlchan, [':', 'JOINCHANNEL', commands[1]])
            self.session.findChannel(commands[1]).addUser(self.name)
            return
        elif(commands[0] == "JOINCHANNEL" and not (commands[1] in self.channel)):
            self.publish(self.ctlchan, [':', 'ERR', 'JOIN_CHANNOTFOUND',commands[1]])
            return
        elif(commands[0] == "JOINCHANNEL" and not (commands[1] in self.channel)):
            self.publish(self.ctlchan,[':','ERR','JOIN_CHANALREADYIN',commands[1]])
            return
        if (commands[0] == "LEAVECHANNEL" and self.session.findChannel(commands[1]) != -1 and (commands[1] in self.channel)):
            self.channel.remove(commands[1])
            self.publish(self.ctlchan, [':', 'LEAVECHANNEL', commands[1]])
            self.session.findChannel(commands[1]).removeUser(self.name)
            return
        elif(commands[0] == "LEAVECHANNEL"):
            self.publish(self.ctlchan, [':', 'ERR', 'LEAVE_CHANNOTFOUND',commands[1]])
            return
        if (commands[0] == "QUIT"):
            await self.__destructor__()
            return
        if (commands[0] == "MKCHANNEL") and (self.session.findChannel(commands[1]) == -1 and commands[1] != ""):
            print('Creating channel with name ' + commands[1])
            self.session.channelarr.append(Channel(commands[1],self.session))
            return
        elif(commands[0] == "MKCHANNEL"):
            self.publish(self.ctlchan, [':', 'ERR', 'MK_CHANALREADYEXISTS',commands[1]])
            return
        if (commands[0] == "RMCHANNEL") and (self.session.findChannel(commands[1]) != -1 and commands[1] != ""):
            print('Deleting channel with name ' + commands[1])
            obj = self.session.findChannel(commands[1])
            if(obj != -1):
                obj.__destructor__()
                self.session.removeChannel(obj)
            return
        elif(commands[0] == "RMCHANNEL"):
            self.publish(self.ctlchan,[':','ERR','RM_CHANNOTFOUND',commands[1]])
            return
        if (commands[0] == "MESSAGE") and (self.session.findChannel(commands[1]) != -1 and commands[1] != ""):
            self.session.findChannel(commands[1]).pushToChannelFromUser(self.name,commands[2])
            return
        if (commands[0] == "CHANNAMES"):
            response = [':','CHANNAMES']
            for channel in self.session.channelarr:
                response.append(channel.name)
            self.publish(self.ctlchan,response)
            return 
    async def __destructor__(self):
        try:
            await self.subscription.unsubscribe()
        except Exception as e:
            print(e)
        if (not self.ft):
            self.session.ruleModify([self.userid,self.audiochan,'register',True,True])
        self.session.ruleModify([self.userid,self.ctlchan,'publish',True,True])
        self.session.ruleModify([self.userid,self.ctlchan,'subscribe',True,True])
        for channel in self.channel:
        	obj = self.session.findChannel(channel)
        	if (obj != -1):
            		obj.removeUser(self.name)
        self.dead = True

class Server(ApplicationSession):
    def isAllowed(self, session, uri, action):
        for rule in self.rulearr:
            if rule.session == session and rule.uri == uri and rule.action == action and rule.allow == True:
               return True
        return False

    def authorize(self, session, uri, action):
        s = {'allow': self.isAllowed(session["session"],uri,action), 'disclose': True, 'cache': True}
        if (uri == 'com.audiomain'):
            s = {'allow': True, 'disclose': True, 'cache': True}
        return s

    def ruleModify(self,command):
        if (not command[4]):
            self.rulearr.append(Rule(command[0], command[1], command[2], command[3]))
        else:
            i = -1
            for rule in range(len(self.rulearr)):
                print(rule)
                if (self.rulearr[rule].session == command[0]) and (self.rulearr[rule].uri == command[1]) and (self.rulearr[rule].action == command[2]) and (self.rulearr[rule].allow == command[3]):
                   i = rule
            if (i != -1):
               del self.rulearr[i]
            
            #self.rulearr.remove(Rule(command[0], command[1], command[2], command[3]))

    async def pruneLoop(self):
        while True:
            await self.pruneUsers()
            await asyncio.sleep(1)

    def findChannel(self,name):
        for channel in self.channelarr:
            if (channel.name == name):
                return channel
        return -1

    def findUser(self,name):
        for user in self.userarr:
            print(name)
            if (user.name == name):
                print(name)
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

    async def pruneUsers(self):
        for user in self.userarr:
            if(((int(time.time() - user.systemtime)) > 10)):
                print("Deleting " + user.name)
                if(not user.dead):
                        await user.__destructor__()
                self.removeUser(user)

    def onMainCtlEvent(self, *command, details):
        if(command[0] == "NICK" and (self.findUser(command[1])) == -1):
            print("Time at connect" + datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S:%f"))
            user = User(command[1], 'com.audioctl.' + command[1], 'com.audiorpc.' + command[1], self, details.publisher)
            self.userarr.append(user)
            user.subscription = yield from self.subscribe(user.ctlCallback, user.ctlchan)
            self.publish('com.audiomain',[':','READY',str(details.publisher),'127.0.0.1'])

    def onConnect(self):
        self.rulearr = []
        self.join(self.config.realm, [u'ticket'],u'god')

    def onChallenge(self, challenge):
        if challenge.method == u'ticket':
            return u'bestpass'
        else:
            raise Exception('Invalid authmethod {}'.format(challenge.method))



    async def onJoin(self, details):
        self.initialize()
        await self.register(self.authorize, u'com.authorizon.auth')
        await self.subscribe(self.onMainCtlEvent, u"com.audiomain", options=SubscribeOptions(details_arg='details'))
        await self.pruneLoop()

    def initialize(self):
        self.userarr = []
        self.channelarr = []


runner = ApplicationRunner(u"ws://127.0.0.1:8080/ws", u"realm1")
runner.run(Server)
