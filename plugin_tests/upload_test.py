#!/usr/bin/env python
# -*- coding: utf-8 -*-

###############################################################################
#  Copyright Kitware Inc.
#
#  Licensed under the Apache License, Version 2.0 ( the "License" );
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
###############################################################################

import datetime
import hashlib
import json
import moto
import os
import re
import requests
import six

from functools import wraps
from xml.etree import ElementTree

from girder.constants import AccessType
from girder.utility import parseTimestamp
from girder.utility.s3_assetstore_adapter import makeBotoConnectParams, S3AssetstoreAdapter
from girder.utility.ziputil import ZipGenerator
from tests import base, mock_s3

from .isic_base import IsicTestCase


def setUpModule():
    base.enabledPlugins.append('isic_archive')
    base.startServer()


def tearDownModule():
    base.stopServer()


def moto_reduce_upload_part_min_size(f):
    """
    Decorator to temporarily decrease the minimum multipart upload part size.
    This avoids the following error response when sending the Complete Multipart
    Upload request:

        <Code>EntityTooSmall</Code>
        <Message>Your proposed upload is smaller than the minimum allowed object size.</Message>

    Based on https://github.com/spulec/moto/blob/b0d5eaf/tests/test_s3/test_s3.py#L40.
    """
    origSize = moto.s3.models.UPLOAD_PART_MIN_SIZE
    reducedSize = 1024

    @wraps(f)
    def wrapped(*args, **kwargs):
        try:
            moto.s3.models.UPLOAD_PART_MIN_SIZE = reducedSize
            return f(*args, **kwargs)
        finally:
            moto.s3.models.UPLOAD_PART_MIN_SIZE = origSize

    return wrapped


class UploadTestCase(IsicTestCase):
    def setUp(self):
        super(UploadTestCase, self).setUp()

        # Set up girder_worker
        from girder.plugins import worker
        Setting = self.model('setting')
        Setting.set(
            worker.PluginSettings.BROKER,
            'mongodb://localhost:27017/girder_worker')
        Setting.set(
            worker.PluginSettings.BACKEND,
            'mongodb://localhost:27017/girder_worker')
        # TODO: change this to 'amqp://guest@127.0.0.1/' for RabbitMQ

        self.testDataDir = os.path.join(
            os.environ['GIRDER_TEST_DATA_PREFIX'], 'plugins', 'isic_archive')

    def _createReviewerUser(self):
        """Create a reviewer user that will receive notification emails."""
        Group = self.model('group')
        User = self.model('user', 'isic_archive')

        resp = self.request(path='/user', method='POST', params={
            'email': 'reviewer-user@isic-archive.com',
            'login': 'reviewer-user',
            'firstName': 'reviewer',
            'lastName': 'user',
            'password': 'password'
        })
        self.assertStatusOk(resp)

        reviewerUser = User.findOne({'login': 'reviewer-user'})
        reviewersGroup = Group.findOne({'name': 'Dataset QC Reviewers'})
        Group.addUser(reviewersGroup, reviewerUser, level=AccessType.READ)

        return reviewerUser

    def _createUploaderUser(self):
        """Create an uploader user."""
        Group = self.model('group')
        User = self.model('user', 'isic_archive')

        resp = self.request(path='/user', method='POST', params={
            'email': 'uploader-user@isic-archive.com',
            'login': 'uploader-user',
            'firstName': 'uploader',
            'lastName': 'user',
            'password': 'password'
        })
        self.assertStatusOk(resp)

        uploaderUser = User.findOne({'login': 'uploader-user'})
        contributorsGroup = Group.findOne({'name': 'Dataset Contributors'})
        Group.addUser(contributorsGroup, uploaderUser, level=AccessType.READ)

        return uploaderUser

    def _createZipFile(self, zipName, zipContentNames):
        """
        Create a zip file of images.
        Returns (stream, size).
        """
        zipStream = six.BytesIO()
        zipGen = ZipGenerator(zipName)
        for fileName in zipContentNames:
            with open(os.path.join(self.testDataDir, fileName), 'rb') as \
                    fileObj:
                for data in zipGen.addFile(lambda: fileObj, fileName):
                    zipStream.write(data)
        zipStream.write(zipGen.footer())
        # Seek to the end of the stream
        zipStream.seek(0, 2)
        zipSize = zipStream.tell()
        zipStream.seek(0)
        return zipStream, zipSize

    def _uploadDataset(self, uploaderUser, zipName, zipContentNames,
                       datasetName, datasetDescription):
        Dataset = self.model('dataset', 'isic_archive')
        Folder = self.model('folder')
        Upload = self.model('upload')

        # Create a ZIP file of images
        zipStream, zipSize = self._createZipFile(zipName, zipContentNames)

        # Create new folders in the uploader user's home
        resp = self.request(
            path='/folder', method='POST', user=uploaderUser, params={
                'parentType': 'user',
                'parentId': str(uploaderUser['_id']),
                'name': '%s_upload_folder' % zipName
            })
        self.assertStatusOk(resp)
        uploadZipFolder = Folder.load(resp.json['_id'], force=True)

        # Uploading files is complicated via REST, so upload the ZIP via models
        # No special behavior should be attached to uploading a plain ZIP file
        zipFile = Upload.uploadFromFile(
            obj=zipStream,
            size=zipSize,
            name='%s.zip' % zipName,
            parentType='folder',
            parent=uploadZipFolder,
            user=uploaderUser,
            mimeType='application/zip'
        )

        resp = self.request(
            path='/dataset', method='POST', user=uploaderUser, params={
                'name': datasetName,
                'description': datasetDescription,
                'license': 'CC-0',
                'attribution': 'Test Organization',
                'owner': 'Test Organization'
            })
        self.assertStatusOk(resp)
        dataset = Dataset.findOne({'name': datasetName})
        self.assertIsNotNone(dataset)
        self.assertEqual(str(dataset['_id']), resp.json['_id'])

        self.assertNoMail()
        resp = self.request(
            path='/dataset/%s/imageZip' % dataset['_id'], method='POST', user=uploaderUser,
            params={
                'zipFileId': zipFile['_id'],
                'signature': 'Test Uploader'
            })
        self.assertStatusOk(resp)
        # Uploader user and reviewer user should receive emails
        self.assertMails(count=2)

        return dataset

    def _base64MD5(self, data):
        """Return Base64-encoded MD5 digest of the data."""
        md5 = hashlib.md5()
        md5.update(data)
        return md5.digest().encode('base64')

    def testUploadDataset(self):
        File = self.model('file')
        Folder = self.model('folder')
        Upload = self.model('upload')
        User = self.model('user', 'isic_archive')

        # Create users
        reviewerUser = self._createReviewerUser()
        uploaderUser = self._createUploaderUser()

        # Create and upload two ZIP files of images
        publicDataset = self._uploadDataset(
            uploaderUser=uploaderUser,
            zipName='test_zip_1',
            zipContentNames=['test_1_small_1.jpg', 'test_1_small_2.jpg',
                             'test_1_large_1.jpg'],
            datasetName='test_dataset_1',
            datasetDescription='A public test dataset'
        )
        privateDataset = self._uploadDataset(
            uploaderUser=uploaderUser,
            zipName='test_zip_2',
            zipContentNames=['test_1_small_3.jpg', 'test_1_large_2.jpg'],
            datasetName='test_dataset_2',
            datasetDescription='A private test dataset'
        )

        # Ensure that ordinary users aren't getting review tasks
        resp = self.request(
            path='/task/me/review', method='GET')
        self.assertStatus(resp, 401)
        resp = self.request(
            path='/task/me/review', method='GET', user=uploaderUser)
        self.assertStatus(resp, 403)

        # Ensure that reviewer users are getting tasks
        resp = self.request(
            path='/task/me/review', method='GET', user=reviewerUser)
        self.assertStatusOk(resp)
        reviewTasks = resp.json
        self.assertEqual(len(reviewTasks), 2)
        self.assertIn({
            'dataset': {
                '_id': str(publicDataset['_id']),
                'name': publicDataset['name']},
            'count': 3
        }, reviewTasks)
        self.assertIn({
            'dataset': {
                '_id': str(privateDataset['_id']),
                'name': privateDataset['name']},
            'count': 2
        }, reviewTasks)

        # Ensure that review task redirects are working
        resp = self.request(
            path='/task/me/review/redirect', method='GET', user=reviewerUser)
        self.assertStatus(resp, 400)
        for reviewTask in reviewTasks:
            reviewId = reviewTask['dataset']['_id']
            resp = self.request(
                path='/task/me/review/redirect', method='GET',
                params={'datasetId': reviewId}, user=reviewerUser, isJson=False)
            self.assertStatus(resp, 307)
            self.assertDictContainsSubset({
                'Location': '/#tasks/review/%s' % reviewId
            }, resp.headers)

        # Accept all images
        resp = self.request(
            path='/dataset/%s/review' % publicDataset['_id'], method='GET', user=reviewerUser)
        self.assertStatusOk(resp)
        self.assertEqual(len(resp.json), 3)
        imageIds = [image['_id'] for image in resp.json]
        resp = self.request(
            path='/dataset/%s/review' % publicDataset['_id'], method='POST', user=reviewerUser,
            params={
                'accepted': json.dumps(imageIds),
                'flagged': []
            })
        self.assertStatusOk(resp)

        # Test metadata registration
        resp = self.request(
            path='/folder', method='POST', user=uploaderUser, params={
                'parentType': 'user',
                'parentId': str(uploaderUser['_id']),
                'name': 'test_1_metadata_folder'
            })
        self.assertStatusOk(resp)
        uploadCsvFolder = Folder.load(resp.json['_id'], force=True)

        # Upload the CSV metadata file
        csvPath = os.path.join(self.testDataDir, 'test_1_metadata.csv')
        with open(csvPath, 'rb') as csvStream:
            metadataFile = Upload.uploadFromFile(
                obj=csvStream,
                size=os.path.getsize(csvPath),
                name='test_1_metadata.csv',
                parentType='folder',
                parent=uploadCsvFolder,
                user=uploaderUser,
                mimeType='text/csv'
            )

        # Attempt to register metadata as invalid users
        resp = self.request(
            path='/dataset/%s/metadata' % publicDataset['_id'], method='POST',
            params={
                'metadataFileId': metadataFile['_id']
            })
        self.assertStatus(resp, 401)
        resp = self.request(
            path='/dataset/%s/metadata' % publicDataset['_id'], method='POST',
            user=reviewerUser, params={
                'metadataFileId': metadataFile['_id']
            })
        self.assertStatus(resp, 403)

        # Attempt to register metadata with invalid parameters
        resp = self.request(
            path='/dataset/%s/metadata' % publicDataset['_id'], method='POST',
            user=uploaderUser)
        self.assertStatus(resp, 400)
        self.assertIn('required', resp.json['message'].lower())
        resp = self.request(
            path='/dataset/%s/metadata' % publicDataset['_id'], method='POST',
            user=uploaderUser, params={
                'metadataFileId': 'bad_id'
            })
        self.assertStatus(resp, 400)
        self.assertIn('invalid', resp.json['message'].lower())
        resp = self.request(
            path='/dataset/%s/metadata' % publicDataset['_id'], method='POST',
            user=uploaderUser, params={
                # TODO: find a cleaner way to pass a file with the wrong format
                'metadataFileId': File.findOne({
                    'mimeType': 'application/zip'})['_id'],
            })
        self.assertStatus(resp, 400)
        self.assertIn('format', resp.json['message'].lower())

        # Attempt to list registered metadata as invalid users
        resp = self.request(
            path='/dataset/%s/metadata' % publicDataset['_id'], method='GET')
        self.assertStatus(resp, 401)
        resp = self.request(
            path='/dataset/%s/metadata' % publicDataset['_id'], method='GET',
            user=uploaderUser)
        self.assertStatus(resp, 403)

        # List (empty) registered metadata
        resp = self.request(
            path='/dataset/%s/metadata' % publicDataset['_id'], method='GET',
            user=reviewerUser)
        self.assertStatusOk(resp)
        self.assertEqual(resp.json, [])

        # Register metadata with dataset
        self.assertNoMail()
        resp = self.request(
            path='/dataset/%s/metadata' % publicDataset['_id'], method='POST',
            user=uploaderUser, params={
                'metadataFileId': metadataFile['_id']
            })
        self.assertStatusOk(resp)
        # Reviewer user should receive email
        self.assertMails(count=1)

        # List registered metadata
        resp = self.request(
            path='/dataset/%s/metadata' % publicDataset['_id'],
            user=reviewerUser)
        self.assertStatusOk(resp)
        self.assertIsInstance(resp.json, list)
        self.assertEqual(len(resp.json), 1)
        # Check the 'time' field separately, as we don't know what it will be
        self.assertIn('time', resp.json[0])
        self.assertLess(parseTimestamp(resp.json[0]['time']),
                        datetime.datetime.utcnow())
        self.assertDictEqual({
            'file': {
                '_id': str(metadataFile['_id']),
                'name': metadataFile['name']
            },
            'user': {
                '_id': str(uploaderUser['_id']),
                'name': User.obfuscatedName(uploaderUser)
            },
            # This is actually checked above
            'time': resp.json[0]['time']
        }, resp.json[0])

        # Test applying metadata
        resp = self.request(
            path='/dataset/%s/metadata/%s' % (publicDataset['_id'], metadataFile['_id']),
            method='POST', user=uploaderUser, params={
                'save': False
            })
        self.assertStatusOk(resp)
        self.assertIn('errors', resp.json)
        self.assertIn('warnings', resp.json)
        self.assertEqual(0, len(resp.json['errors']))
        self.assertEqual(
            resp.json['warnings'], [
                {'description':
                 'on CSV row 4: no images found that match u\'filename\': u\'test_1_small_3.jpg\''},
                {'description':
                 'on CSV row 6: no images found that match u\'filename\': u\'test_1_large_2.jpg\''},
                {'description':
                 'unrecognized field u\'age_approx\' will be added to unstructured metadata'},
                {'description':
                 'unrecognized field u\'isic_source_name\' will be added to unstructured metadata'}
            ])

    def testUploadImages(self):
        """
        Test creating dataset, uploading images to the dataset individually, and applying metadata
        to an uploading image.
        """
        # Create users
        reviewerUser = self._createReviewerUser()
        uploaderUser = self._createUploaderUser()

        # Create a dataset
        resp = self.request(path='/dataset', method='POST', user=uploaderUser, params={
            'name': 'test_dataset_1',
            'description': 'A public test dataset',
            'license': 'CC-0',
            'attribution': 'Test Organization',
            'owner': 'Test Organization'
        })
        self.assertStatusOk(resp)
        dataset = resp.json

        # Add images to the dataset
        for imageName in ['test_1_small_1.jpg', 'test_1_large_1.jpg']:
            with open(os.path.join(self.testDataDir, imageName), 'rb') as fileObj:
                fileData = fileObj.read()

            resp = self.request(
                path='/dataset/%s/image' % dataset['_id'], method='POST', user=uploaderUser,
                body=fileData, type='image/jpeg', isJson=False,
                params={
                    'filename': imageName,
                    'signature': 'Test Uploader'
                })
            self.assertStatusOk(resp)

        # Accept all images
        resp = self.request(
            path='/dataset/%s/review' % dataset['_id'], method='GET', user=reviewerUser)
        self.assertStatusOk(resp)
        self.assertEqual(2, len(resp.json))
        imageIds = [image['_id'] for image in resp.json]
        resp = self.request(
            path='/dataset/%s/review' % dataset['_id'], method='POST', user=reviewerUser,
            params={
                'accepted': json.dumps(imageIds),
                'flagged': []
            })
        self.assertStatusOk(resp)

        # Check number of images in dataset
        resp = self.request(path='/dataset/%s' % dataset['_id'], user=uploaderUser)
        self.assertStatusOk(resp)
        dataset = resp.json
        self.assertEqual(2, dataset['count'])

        # Add metadata to images
        resp = self.request(path='/image', user=uploaderUser, params={
            'datasetId': dataset['_id']
        })
        self.assertStatusOk(resp)
        self.assertEqual(2, len(resp.json))
        image = resp.json[0]

        metadata = {
            'diagnosis': 'melanoma',
            'benign_malignant': 'benign'
        }
        resp = self.request(
            path='/image/%s/metadata' % image['_id'], method='POST',
            user=uploaderUser, body=json.dumps(metadata), type='application/json', params={
                'save': False
            })
        self.assertStatusOk(resp)
        self.assertIn('errors', resp.json)
        self.assertIn('warnings', resp.json)
        self.assertEqual(1, len(resp.json['errors']))
        self.assertEqual([], resp.json['warnings'])

        metadata = {
            'diagnosis': 'melanoma',
            'benign_malignant': 'malignant',
            'diagnosis_confirm_type': 'histopathology',
            'custom_id': '111-222-3334'
        }
        resp = self.request(
            path='/image/%s/metadata' % image['_id'], method='POST',
            user=uploaderUser, body=json.dumps(metadata), type='application/json', params={
                'save': True
            })
        self.assertStatusOk(resp)
        self.assertIn('errors', resp.json)
        self.assertIn('warnings', resp.json)
        self.assertEqual([], resp.json['errors'])
        self.assertEqual(1, len(resp.json['warnings']))

        # Verify that metadata exists on image
        resp = self.request(path='/image/%s' % image['_id'], user=uploaderUser)
        self.assertStatusOk(resp)
        self.assertEqual('melanoma', resp.json['meta']['clinical']['diagnosis'])
        self.assertEqual('malignant', resp.json['meta']['clinical']['benign_malignant'])
        self.assertEqual('histopathology', resp.json['meta']['clinical']['diagnosis_confirm_type'])
        self.assertEqual('111-222-3334', resp.json['meta']['unstructured']['custom_id'])

    @moto.mock_s3
    def testUploadDatasetS3(self):
        Assetstore = self.model('assetstore')
        Image = self.model('image', 'isic_archive')
        Setting = self.model('setting')

        # Create user
        user = self._createUploaderUser()

        # Create an S3 bucket to use with the assetstore
        botoParams = makeBotoConnectParams('access', 'secret')
        mock_s3.createBucket(botoParams, 'zip-uploads')

        # Create an S3 assetstore
        assetstore = Assetstore.createS3Assetstore(
            name='test', bucket='zip-uploads', accessKeyId='access', secret='secret', prefix='test')

        # Configure the ZIP upload S3 assetstore
        Setting.set('isic.zip_upload_s3_assetstore_id', assetstore['_id'])

        # Create a ZIP file of images
        zipName = 'test_zip_1'
        zipStream, zipSize = self._createZipFile(
            zipName=zipName, zipContentNames=['test_1_small_1.jpg', 'test_1_small_2.jpg'])
        self.assertLessEqual(zipSize, S3AssetstoreAdapter.CHUNK_LEN)

        # Create a dataset
        datasetName = 'test_dataset_1'
        resp = self.request(
            path='/dataset', method='POST', user=user, params={
                'name': datasetName,
                'description': 'A public test dataset',
                'license': 'CC-0',
                'attribution': 'Test Organization',
                'owner': 'Test Organization'
            })
        self.assertStatusOk(resp)
        dataset = resp.json

        # Start a new upload of the ZIP file and get S3 request information from server
        resp = self.request(
            path='/dataset/%s/zip' % dataset['_id'], method='POST', user=user, params={
                'name': zipName,
                'size': zipSize
            })
        self.assertStatusOk(resp)
        upload = resp.json
        self.assertIn('s3', upload)
        self.assertHasKeys(upload['s3'], ['chunked', 'request'])
        self.assertFalse(upload['s3']['chunked'])
        s3Request = upload['s3']['request']
        self.assertHasKeys(s3Request, ['method', 'url', 'headers'])

        # Upload directly to S3 using request information from server
        # https://docs.aws.amazon.com/AmazonS3/latest/dev/UploadObjSingleOpREST.html
        chunk = zipStream.read()
        s3Request['headers'].update({
            'Content-Length': str(zipSize),
            'Content-MD5': self._base64MD5(chunk)
        })
        resp = requests.request(
            s3Request['method'], headers=s3Request['headers'], url=s3Request['url'], data=chunk)
        resp.raise_for_status()

        # Finalize upload
        resp = self.request(
            path='/dataset/%s/zip/%s/completion' % (dataset['_id'], upload['_id']), method='POST',
            user=user)
        self.assertStatusOk(resp)
        zipFile = resp.json
        self.assertEqual('file', zipFile['_modelType'])
        self.assertIn('itemId', zipFile)
        self.assertEqual(zipName, zipFile['name'])
        self.assertEqual(zipSize, zipFile['size'])
        self.assertNotIn('s3', zipFile)

        # Add the images in the ZIP file to the dataset
        self.assertEqual(0, Image.find().count())
        resp = self.request(
            path='/dataset/%s/imageZip' % dataset['_id'], method='POST', user=user,
            params={
                'zipFileId': zipFile['_id'],
                'signature': 'Test Uploader'
            })
        self.assertStatusOk(resp)
        self.assertEqual(2, Image.find().count())

    @moto_reduce_upload_part_min_size
    @moto.mock_s3
    def testUploadDatasetS3Chunked(self):
        Assetstore = self.model('assetstore')
        Image = self.model('image', 'isic_archive')
        Setting = self.model('setting')

        # Create user
        user = self._createUploaderUser()

        # Create an S3 bucket to use with the assetstore
        botoParams = makeBotoConnectParams('access', 'secret')
        mock_s3.createBucket(botoParams, 'zip-uploads')

        # Create an S3 assetstore
        assetstore = Assetstore.createS3Assetstore(
            name='test', bucket='zip-uploads', accessKeyId='access', secret='secret', prefix='test')

        # Configure the ZIP upload S3 assetstore
        Setting.set('isic.zip_upload_s3_assetstore_id', assetstore['_id'])

        # Create a ZIP file of images
        zipName = 'test_zip_1'
        zipStream, zipSize = self._createZipFile(
            zipName=zipName, zipContentNames=['test_1_small_1.jpg', 'test_1_small_2.jpg'])

        # Set assetstore adapter chunk length so that 2 chunks are required for this file
        chunkLength = (zipSize + 1) // 2
        S3AssetstoreAdapter.CHUNK_LEN = chunkLength

        # Create a dataset
        datasetName = 'test_dataset_1'
        resp = self.request(
            path='/dataset', method='POST', user=user, params={
                'name': datasetName,
                'description': 'A public test dataset',
                'license': 'CC-0',
                'attribution': 'Test Organization',
                'owner': 'Test Organization'
            })
        self.assertStatusOk(resp)
        dataset = resp.json

        # Start a new upload of the ZIP file
        # https://docs.aws.amazon.com/AmazonS3/latest/dev/UsingRESTAPImpUpload.html
        resp = self.request(
            path='/dataset/%s/zip' % dataset['_id'], method='POST', user=user, params={
                'name': zipName,
                'size': zipSize
            })
        self.assertStatusOk(resp)
        upload = resp.json
        self.assertIn('s3', upload)
        self.assertHasKeys(upload['s3'], ['chunked', 'chunkLength', 'request'])
        self.assertTrue(upload['s3']['chunked'])
        self.assertEqual(chunkLength, upload['s3']['chunkLength'])
        s3Request = upload['s3']['request']
        self.assertHasKeys(s3Request, ['method', 'url', 'headers'])

        # Initialize direct upload to S3 using request information from server
        # https://docs.aws.amazon.com/AmazonS3/latest/API/mpUploadInitiate.html
        resp = requests.request(
            s3Request['method'], headers=s3Request['headers'], url=s3Request['url'])
        resp.raise_for_status()

        # Parse upload ID from S3 response
        searchResult = re.search(r'<UploadId>(.+)<\/UploadId>', resp.content)
        self.assertIsNotNone(searchResult)
        s3UploadId = searchResult.group(1)

        eTags = []
        contentLength = chunkLength

        # Get S3 request information from server
        resp = self.request(
            path='/dataset/%s/zip/%s/part' % (dataset['_id'], upload['_id']), method='POST',
            user=user, params={
                's3UploadId': s3UploadId,
                'partNumber': 1,
                'contentLength': contentLength
            })
        self.assertStatusOk(resp)
        upload = resp.json
        self.assertIn('s3', upload)
        self.assertIn('chunked', upload['s3'])
        self.assertTrue(upload['s3']['chunked'])
        self.assertIn('request', upload['s3'])
        s3Request = upload['s3']['request']
        self.assertHasKeys(s3Request, ['method', 'url', 'headers'])

        # Upload part directly to S3 using request information from server
        # https://docs.aws.amazon.com/AmazonS3/latest/API/mpUploadUploadPart.html
        part = zipStream.read(contentLength)
        s3Request['headers'].update({
            'Content-Length': str(contentLength),
            'Content-MD5': self._base64MD5(part)
        })
        resp = requests.request(
            s3Request['method'], headers=s3Request['headers'], url=s3Request['url'], data=part)
        resp.raise_for_status()
        self.assertIn('ETag', resp.headers)

        # Store entity tag
        eTags.append(resp.headers['ETag'])

        contentLength = zipSize - chunkLength

        # Check that this is the last chunk
        self.assertLessEqual(contentLength, chunkLength)

        # Get S3 request information from server
        resp = self.request(
            path='/dataset/%s/zip/%s/part' % (dataset['_id'], upload['_id']), method='POST',
            user=user, params={
                's3UploadId': s3UploadId,
                'partNumber': 2,
                'contentLength': contentLength
            })
        self.assertStatusOk(resp)
        upload = resp.json
        self.assertIn('s3', upload)
        self.assertHasKeys(upload['s3'], ['chunked', 'chunkLength', 'request'])
        self.assertTrue(upload['s3']['chunked'])
        self.assertEqual(chunkLength, upload['s3']['chunkLength'])
        s3Request = upload['s3']['request']
        self.assertHasKeys(s3Request, ['method', 'url', 'headers'])

        # Upload next part to S3
        part = zipStream.read(contentLength)
        s3Request['headers'].update({
            'Content-Length': str(contentLength),
            'Content-MD5': self._base64MD5(part)
        })
        resp = requests.request(
            s3Request['method'], headers=s3Request['headers'], url=s3Request['url'], data=part)
        resp.raise_for_status()
        self.assertIn('ETag', resp.headers)

        # Store entity tag
        eTags.append(resp.headers['ETag'])

        # Finalize upload and get S3 request information from server
        resp = self.request(
            path='/dataset/%s/zip/%s/completion' % (dataset['_id'], upload['_id']), method='POST',
            user=user)
        self.assertStatusOk(resp)
        zipFile = resp.json
        self.assertEqual('file', zipFile['_modelType'])
        self.assertIn('itemId', zipFile)
        self.assertEqual(zipName, zipFile['name'])
        self.assertEqual(zipSize, zipFile['size'])
        self.assertIn('s3', zipFile)
        self.assertIn('request', zipFile['s3'])
        s3Request = zipFile['s3']['request']
        self.assertHasKeys(s3Request, ['method', 'url', 'headers'])

        # Complete S3 multipart upload using request information from server
        # and data from previous S3 responses
        # https://docs.aws.amazon.com/AmazonS3/latest/API/mpUploadComplete.html

        # Generate S3 completion request content XML string:
        #     <CompleteMultipartUpload>
        #     <Part>
        #         <PartNumber>PartNumber</PartNumber>
        #         <ETag>ETag</ETag>
        #     </Part>
        #     ...
        #     </CompleteMultipartUpload>
        rootElement = ElementTree.Element('CompleteMultipartUpload')
        for partNumber, eTag in enumerate(eTags, 1):
            partElement = ElementTree.SubElement(rootElement, 'Part')
            partNumberElement = ElementTree.SubElement(partElement, 'PartNumber')
            partNumberElement.text = str(partNumber)
            eTagElement = ElementTree.SubElement(partElement, 'ETag')
            eTagElement.text = eTag

        # Convert ElementTree to string, removing <xml></xml> header
        data = ElementTree.tostring(rootElement, encoding='UTF-8')
        matchResult = re.match(r'<\?xml.*\?>\n?(.*)', data)
        self.assertIsNotNone(matchResult)
        data = matchResult.group(1)

        # Send S3 completion request
        s3Request['headers'].update({
            'Content-Length': str(len(data)),
            'Content-MD5': self._base64MD5(data)
        })
        resp = requests.request(
            s3Request['method'], headers=s3Request['headers'], url=s3Request['url'], data=data)
        resp.raise_for_status()

        # Add the images in the ZIP file to the dataset
        self.assertEqual(0, Image.find().count())
        resp = self.request(
            path='/dataset/%s/imageZip' % dataset['_id'], method='POST', user=user,
            params={
                'zipFileId': zipFile['_id'],
                'signature': 'Test Uploader'
            })
        self.assertStatusOk(resp)
        self.assertEqual(2, Image.find().count())
