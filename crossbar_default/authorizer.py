from autobahn.twisted.wamp import ApplicationSession
from twisted.internet.defer import inlineCallbacks

class Authorizon(ApplicationSession):

    def onConnect(self):
        self.join(self.config.realm, [u'ticket'],u'authorizon')

    def onChallenge(self, challenge):
        if challenge.method == u'ticket':
            return u'testpass'
        else:
            raise Exception('Invalid authmethod {}'.format(challenge.method))

    @inlineCallbacks
    def onJoin(self,details):
        yield self.register(self.authorize, u'com.authorizon.auth')

    def authorize(self, session, uri, action):
        self.log.info('authorize: session={session}, uri={uri}, action={action}',session=session, uri=uri, action=action)
        return True
