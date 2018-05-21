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
import json
import os

from six import BytesIO

from girder.constants import AccessType
from girder.utility import parseTimestamp
from girder.utility.ziputil import ZipGenerator
from tests import base

from .isic_base import IsicTestCase


def setUpModule():
    base.enabledPlugins.append('isic_archive')
    base.startServer()


def tearDownModule():
    base.stopServer()


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

    def _uploadDataset(self, uploaderUser, zipName, zipContentNames,
                       datasetName, datasetDescription):
        Dataset = self.model('dataset', 'isic_archive')
        Folder = self.model('folder')
        Upload = self.model('upload')

        # Create a ZIP file of images
        zipStream = BytesIO()
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
            path='/dataset/%s/zip' % dataset['_id'], method='POST', user=uploaderUser, params={
                'zipFileId': str(zipFile['_id']),
                'signature': 'Test Uploader'
            })
        self.assertStatusOk(resp)
        # Uploader user and reviewer user should receive emails
        self.assertMails(count=2)

        return dataset

    def testUploadDataset(self):
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

        # Attempt to register metadata as invalid users
        csvPath = os.path.join(self.testDataDir, 'test_1_metadata.csv')
        with open(csvPath, 'rb') as csvStream:
            resp = self.request(
                path='/dataset/%s/metadata' % publicDataset['_id'], method='POST',
                body=csvStream.read(), type='text/csv',
                params={
                    'filename': 'test_1_metadata.csv'
                })
            self.assertStatus(resp, 401)

        # Attempt to register metadata with invalid parameters
        with open(csvPath, 'rb') as csvStream:
            resp = self.request(
                path='/dataset/%s/metadata' % publicDataset['_id'], method='POST',
                body=csvStream.read(), type='text/csv',
                user=uploaderUser)
            self.assertStatus(resp, 400)
        self.assertIn('"filename" is required', resp.json['message'].lower())
        with open(csvPath, 'rb') as csvStream:
            resp = self.request(
                path='/dataset/%s/metadata' % publicDataset['_id'], method='POST',
                body=csvStream.read(), type='text/csv',
                user=uploaderUser, params={
                    'filename': ' '
                })
        self.assertStatus(resp, 400)
        self.assertIn('filename must be specified', resp.json['message'].lower())

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
        with open(csvPath, 'rb') as csvStream:
            resp = self.request(
                path='/dataset/%s/metadata' % publicDataset['_id'], method='POST',
                body=csvStream.read(), type='text/csv', isJson=False,
                user=uploaderUser, params={
                    'filename': 'test_1_metadata.csv'
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

        # Check file field
        self.assertIn('file', resp.json[0])
        self.assertIn('_id', resp.json[0]['file'])
        self.assertIn('name', resp.json[0]['file'])
        self.assertEqual('test_1_metadata.csv', resp.json[0]['file']['name'])
        self.assertIn('user', resp.json[0])

        # Check user field
        self.assertDictEqual({
            '_id': str(uploaderUser['_id']),
            'name': User.obfuscatedName(uploaderUser)
        }, resp.json[0]['user'])

        # Check time field
        self.assertIn('time', resp.json[0])
        self.assertLess(parseTimestamp(resp.json[0]['time']),
                        datetime.datetime.utcnow())
        metadataFileId = resp.json[0]['file']['_id']

        # Test applying metadata
        resp = self.request(
            path='/dataset/%s/metadata/%s' % (publicDataset['_id'], metadataFileId),
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
