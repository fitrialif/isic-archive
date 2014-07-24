
from girder.utility.model_importer import ModelImporter
from girder.api.describe import Description
import cherrypy
import os


## returns a standard thumbnail

def thumbnailhandler(id, params):

    m = ModelImporter()
    item = m.model('item').load(id, force=True)
    files = m.model('item').childFiles(item, limit=1)

    firstFile = None
    for f in files:
        firstFile = f
    assetstore = m.model('assetstore').load(firstFile['assetstoreId'])

    # have to fake it for IIP to place nice
    file_path = os.path.join(assetstore['root'], firstFile['path'] + '.tif')
    thumbnail_url = '/fcgi-bin/iipsrv.fcgi?FIF=%s&WID=256&CVT=jpeg' % (file_path)

    raise cherrypy.HTTPRedirect(thumbnail_url)


thumbnailhandler.description = (
    Description('Retrieve the thumbnail for a given item.')
    .param('id', 'The item ID', paramType='path')
    .errorResponse())



## returns the zoomify metadata

def zoomifyhandler(id, params):

    m = ModelImporter()
    item = m.model('item').load(id, force=True)
    files = m.model('item').childFiles(item, limit=1)

    firstFile = None
    for f in files:
        firstFile = f
    assetstore = m.model('assetstore').load(firstFile['assetstoreId'])

    # have to fake it for IIP to place nice
    file_path = os.path.join(assetstore['root'], firstFile['path'] + '.tif')
    zoomify_url = '/fcgi-bin/iipsrv.fcgi?Zoomify=%s/ImageProperties.xml' % (file_path)

    raise cherrypy.HTTPRedirect(zoomify_url)


zoomifyhandler.description = (
    Description('Retrieves the zoomify xml for a given item.')
    .param('id', 'The item ID', paramType='path')
    .errorResponse())



def load(info):
    info['apiRoot'].item.route('GET', (':id', 'thumbnail'), thumbnailhandler)
    info['apiRoot'].item.route('GET', (':id', 'zoomify'), zoomifyhandler)

    # add the base directory to serve

    app_base = os.path.join(os.curdir, os.pardir)
    qc_app_path = os.path.join(app_base, 'qcapp')

    info['config']['/uda'] = {
        'tools.staticdir.on': 'True',
        'tools.staticdir.dir': qc_app_path
    }
