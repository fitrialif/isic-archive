
from girder import events
from girder.constants import TerminalColor
from girder.utility.model_importer import ModelImporter

from pprint import pprint as pp
import zipfile
import mimetypes

from hashlib import sha512
import os
import tempfile
import stat



# zip file upload of packed images

def load(info):

    m = ModelImporter()

    print TerminalColor.info('Started DropZip plugin')

    # if uda study collection not present, create
    uda_user = m.model('user').find({'firstName' : 'uda'})

    if uda_user.count() == 0:

        print TerminalColor.info('No UDA user found, breaking')
        return

    else:

        uda_coll = m.model('collection').find({'name': 'uda'})

        parent_coll = None

        if uda_coll.count() == 0:

            print TerminalColor.info('No UDA collection found, creating')

            uda_user_info = uda_user[0]
            collection = m.model('collection').createCollection('uda', uda_user_info, 'The catch all UDA collection', public=False)

            parent_coll = collection[0]

        else:

            parent_coll = uda_coll[0]


        uda_user_info = uda_user[0]



        print TerminalColor.info('Verifying folders')

        dropzipfolder = m.model('folder').find(
            { '$and' : [
                {'parentId': parent_coll['_id']},
                {'name': 'dropzip'}
            ]})

        if dropzipfolder.count() == 0:
            dzfolder = m.model('folder').createFolder(parent_coll, 'dropzip', '', parentType='collection', public=False, creator=uda_user_info)
            print TerminalColor.info('creating DropZip folder')
            print dzfolder

        else:

            print TerminalColor.info('Found DropZip folder, ready to go!')
            print dropzipfolder[0]


        dropcsv = m.model('folder').find(
            { '$and' : [
                {'parentId': parent_coll['_id']},
                {'name': 'dropcsv'}
            ]})

        if dropcsv.count() == 0:
            dcfolder = m.model('folder').createFolder(parent_coll, 'dropcsv', '', parentType='collection', public=False, creator=uda_user_info)
            print TerminalColor.info('creating Dropcsv folder')
            print dcfolder

        else:

            print TerminalColor.info('Found DropCSV folder, ready to go!')
            print dropcsv[0]



def createFileInternal(assetstore, filehandle_to_read, file_name):


    tempDir = os.path.join(assetstore['root'], 'temp')

    fd, tmppath = tempfile.mkstemp(dir=tempDir)
    os.close(fd)

    fout = open(tmppath, 'w')

    checksum = sha512()

    buf = filehandle_to_read.read()
    checksum.update(buf)
    fout.write(buf)

    fout.close()
    filehandle_to_read.close()

    hash = checksum.hexdigest()
    dir = os.path.join(hash[0:2], hash[2:4])
    absdir = os.path.join(assetstore['root'], dir)

    path = os.path.join(dir, hash)
    abspath = os.path.join(assetstore['root'], path)

    if not os.path.exists(absdir):
        os.makedirs(absdir)

    if os.path.exists(abspath):
        # Already have this file stored, just delete temp file.
        print 'already exists, removing %s' % (tmppath)
        os.remove(tmppath)

    else:
        # Move the temp file to permanent location in the assetstore.
        print 'new file, moving and removing temp %s' % (tmppath)
        os.rename(tmppath, abspath)
        os.chmod(abspath, stat.S_IRUSR | stat.S_IWUSR)

    return {
        'sha512' : hash,
        'path' : path
    }





def uploadHandler(event):

    m = ModelImporter()

    pp(event.info)

    file_info = event.info['file']
    asset_store_info = event.info['assetstore']

    assetstore = m.model('assetstore').load(asset_store_info['_id'])

    item = m.model('item').load(file_info['itemId'], force=True)
    folder = m.model('folder').load(item['folderId'], force=True)

    uda_coll = m.model('collection').find({'name': 'uda'})[0]
    uda_user = m.model('user').find({'firstName' : 'uda'})[0]

    print item
    print folder

    if folder['name'] == 'dropzip':


        if file_info['mimeType'] == 'application/zip':

            full_file_path = os.path.join(asset_store_info['root'], file_info['path'])

            zf = zipfile.ZipFile(open(full_file_path))
            base_file_name = file_info['name'].split('.')[0]
            print TerminalColor.info('Creating folder %s' % base_file_name)

            # test whether folder exists
            newfolder = m.model('folder').find({'name': base_file_name})

            if newfolder.count() != 0:

                print TerminalColor.error('folder already exists, extracting again')

                for zfile in zf.infolist():

                    guessed_mime = mimetypes.guess_type(zfile.filename)

                    # if guessed_mime[0] == 'image/jpeg':
                    #
                    z = zf.open(zfile)
                    new_file_dict = createFileInternal(assetstore, z, zfile.filename)

                    newitem = m.model('item').createItem(
                        name=zfile.filename, creator=uda_user,
                        folder=newfolder[0])

                    print guessed_mime

                    file_entry= m.model('file').createFile(
                        item=newitem, name=zfile.filename, size=zfile.file_size,
                        creator=uda_user, assetstore=assetstore,
                        mimeType=guessed_mime[0])

                    file_entry['sha512'] = new_file_dict['sha512']
                    file_entry['path'] = new_file_dict['path']

                    m.model('file').save(file_entry)

            else:
                print TerminalColor.info('folder doesnt exist, creating')

                createdfolder = m.model('folder').createFolder(uda_coll, base_file_name, 'Dropzip generated folder', parentType='collection', public=False, creator=uda_user)

                for zfile in zf.infolist():

                    z = zf.open(zfile)
                    new_file_dict = createFileInternal(assetstore, z, zfile.filename)

                    newitem = m.model('item').createItem(
                        name=zfile.filename, creator=uda_user,
                        folder=createdfolder)

                    guessed_mime = mimetypes.guess_type(zfile.filename)
                    print guessed_mime

                    file_entry= m.model('file').createFile(
                        item=newitem, name=zfile.filename, size=zfile.file_size,
                        creator=uda_user, assetstore=assetstore,
                        mimeType=guessed_mime[0])

                    file_entry['sha512'] = new_file_dict['sha512']
                    file_entry['path'] = new_file_dict['path']

                    m.model('file').save(file_entry)

                    pp(file)


        # delete this item since we don't care about it
        m.model('item').remove(item)


    elif folder['name'] == 'dropcsv':

        if file_info['mimeType'] == 'text/csv':

            full_file_path = os.path.join(asset_store_info['root'], file_info['path'])

            import csv

            firstRow = True

            col_headers = []

            with open(full_file_path, 'rU') as csvfile:
                csvread = csv.reader(csvfile, delimiter=',', quotechar='"')
                for row in csvread:

                    if firstRow:

                        col_headers = row
                        firstRow = False

                    else:

                        id_index = col_headers.index('isic_id')

                        possible_item = m.model('item').find({
                            'name' : row[id_index] + '.jpg'
                        })

                        if possible_item.count() > 0:
                            #
                            # print possible_item[0]

                            new_metadata = dict(zip(col_headers, row))

                            m.model('item').setMetadata(possible_item[0], new_metadata)



                        # print row[id_index]




        m.model('item').remove(item)





events.bind('data.process', 'uploadHandler', uploadHandler)
