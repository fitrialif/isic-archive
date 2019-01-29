from celery import Celery
from celery.signals import worker_ready
from celery.utils.log import get_task_logger
import jsonpickle
from kombu.serialization import register
import pymongo
import sentry_sdk

from girder.constants import TokenScope
from girder.models.token import Token
from girder.models.user import User
from girder.utility import mail_utils

app = Celery()


class CeleryAppConfig(object):
    # jsonpickle is used to support passing object ids between tasks
    task_serializer = 'jsonpickle'


app.config_from_object(CeleryAppConfig())

task_logger = get_task_logger(__name__)
sentry_sdk.init()


@app.on_after_configure.connect
def setupPeriodicTasks(sender, **kwargs):
    sender.add_periodic_task(30, maybeSendIngestionNotifications.s(),
                             name='Send any necessary notifications for ingested batches.')

@app.on_after_configure.connect
def fixGirderImports(sender, **kwargs):
    from girder.utility.server import configureServer
    configureServer(curConfig={
        'server': {
            'mode': 'production'
        },
        'cherrypy_server': False
    })


class CredentialedGirderTask(app.Task):
    """
    Provide a celery task with access to a Girder token via self.token.

    This base task should always be used in conjunction with setting bind=True in order
    to access the token.
    """
    def __call__(self, *args, **kwargs):
        """
        The child class overrides run, so __call__ must be used to hook in before a task
        is executed.
        """
        from girder.plugins.isic_archive.provision_utility import getAdminUser
        self.token = Token().createToken(user=getAdminUser(), days=1,
                                         scope=[TokenScope.DATA_READ, TokenScope.DATA_WRITE])
        self.token = str(self.token['_id'])

        super(CredentialedGirderTask, self).__call__(*args, **kwargs)


register('jsonpickle', jsonpickle.encode, jsonpickle.decode, content_type='application/json',
         content_encoding='utf-8')


@app.task()
def maybeSendIngestionNotifications():
    from girder.plugins.isic_archive.models.batch import Batch
    from girder.plugins.isic_archive.models.image import Image
    for batch in Batch().find({'ingestStatus': 'extracted'}):
        if not Batch().hasImagesPendingIngest(batch):
            # TODO: Move sorting to templating since it's a rendering concern?
            failedImages = list(Image().find({
                '$and': [
                    {'meta.batchId': batch['_id']},
                    {'$or': [
                        {'ingestionState.largeImage': False},
                        {'ingestionState.superpixelMask': False}
                    ]
                    }
                ]
            }, fields=['privateMeta.originalFilename']).sort(
                'privateMeta.originalFilename',
                pymongo.ASCENDING
            ))
            skippedFilenames = list(Image().find({
                '$and': [
                    {'meta.batchId': batch['_id']},
                    {'readable': False}
                ]
            }, fields=['privateMeta.originalFilename']).sort(
                'privateMeta.originalFilename',
                pymongo.ASCENDING
            ))

            sendIngestionNotification.delay(batch['_id'], failedImages, skippedFilenames)
            batch['ingestStatus'] = 'notified'
            Batch().save(batch)


@app.task()
def sendIngestionNotification(batchId, failedImages, skippedFilenames):
    from girder.plugins.isic_archive.models.batch import Batch
    from girder.plugins.isic_archive.models.dataset import Dataset
    from girder.plugins.isic_archive.utility.mail_utils import sendEmail, sendEmailToGroup
    batch = Batch().load(batchId)
    dataset = Dataset().load(batch['datasetId'], force=True)
    user = User().load(batch['creatorId'], force=True)
    host = mail_utils.getEmailUrlPrefix()
    # TODO: The email should gracefully handle the situation where failedImages or skippedFilenames
    # has an excessive amount of items.
    params = {
        'isOriginalUploader': True,
        'host': host,
        'dataset': dataset,
        # We intentionally leak full user details here, even though all
        # email recipients may not have access permissions to the user
        'user': user,
        'batch': batch,
        'failedImages': failedImages,
        'skippedFilenames': skippedFilenames
    }
    subject = 'ISIC Archive: Dataset Upload Confirmation'
    templateFilename = 'ingestDatasetConfirmation.mako'

    # Mail user
    html = mail_utils.renderTemplate(templateFilename, params)
    sendEmail(to=user['email'], subject=subject, text=html)

    # Mail 'Dataset QC Reviewers' group
    params['isOriginalUploader'] = False
    sendEmailToGroup(
        groupName='Dataset QC Reviewers',
        templateFilename=templateFilename,
        templateParams=params,
        subject=subject)
