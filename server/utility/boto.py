from boto3.session import Session

from girder.utility.config import getConfig

developmentMode = getConfig()['server']['mode'] == 'development'

if developmentMode:
    s3Kwargs = {
        'endpoint_url': 'http://localhost:4572'
    }

session = Session()
s3 = session.client('s3', **s3Kwargs)
sts = session.client('sts')

if developmentMode:
    def mockStsAssumeRole(*args, **kwargs):
        return {
            'Credentials':
                {
                    'AccessKeyId': 'foo',
                    'SecretAccessKey': 'bar',
                    'SessionToken': 'baz'
                }
        }

    sts.assume_role = mockStsAssumeRole
