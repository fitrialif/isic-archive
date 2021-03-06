'use strict';
/*global derm_app, $, console*/
/*jslint browser: true*/

var derm_app = angular.module('DermApp');

function externalApply() {
    var scope = angular.element($("#angular_id")).scope();
    if (!scope.$root.$$phase) {
        scope.$apply();
    }
}

var olViewer = derm_app.factory('olViewer',
    function (ol, $http, $log) {

        var olViewer = function (mapContainer) {

            $log.debug('Creating olViewer:', this);

            var self = this;

            // Instance variables
            this.image_layer = undefined;
            self.image_metadata = undefined;

            this.map = undefined;
            this.draw_mode = undefined;
            this.draw_label = undefined;

            this.last_click_location = undefined;
            this.last_job_id = undefined;
            this.fill_tolerance = 50;

            this.paint_size = 70;

//            this.select_interaction = new ol.interaction.Select();
//            this.selected_features = this.select_interaction.getFeatures();
//            var collection = select.getFeatures();
//            this.selected_features.on('add', function(e){
//                $log.debug('add', e);
//            });
//            this.selected_features.on('remove', function(e){
//                $log.debug('remove', e);
//            });

            // annotations added that need to be saved
//            this.clearTemporaryAnnotations();

            // current list of features
            // annotations previously saved

            var styleFunction = (function () {
                return function (feature, resolution) {
                    if (feature.get('hexcolor')) {
                        return [
                            new ol.style.Style({
                                stroke: new ol.style.Stroke({
                                    color: feature.get('hexcolor'),
                                    width: 2
                                }),
                                fill: new ol.style.Fill({
                                    color: feature.get('rgbcolor')
                                })
                            })
                        ];
                    } else {
                        return [
                            new ol.style.Style({
                                fill: new ol.style.Fill({
                                    color: 'rgba(255, 255, 255, 0.2)'
                                }),
                                stroke: new ol.style.Stroke({
                                    color: '#000000',
                                    width: 0
                                }),
                                image: new ol.style.Circle({
                                    radius: 0,
                                    fill: new ol.style.Fill({
                                        color: '#000000'
                                    })
                                })
                            })
                        ];
                    }
                };
            })();

            this.vector_source = new ol.source.Vector({
                wrapX: false
            });
            this.vector_layer = new ol.layer.Vector({
                source: this.vector_source,
                style: styleFunction
            });

            this.draw_interaction = new ol.interaction.Draw({
                source: this.vector_source,
                type: 'Polygon'
            });

            this.draw_interaction.on('drawend', function (e) {
                var properties;

                if (self.draw_label === 'lesion') {
                    properties = {
                        icon: 'static/derm/images/lesion.jpg',
                        hexcolor: '#ff0000',
                        source: 'manual pointlist',
                        title: self.draw_label,
                        rgbcolor: 'rgba(255, 255, 255, 0.1)'
                    };
                } else if (self.draw_label === 'normal') {
                    properties = {
                        icon: 'static/derm/images/normal.jpg',
                        hexcolor: '#0099ff',
                        source: 'manual pointlist',
                        title: self.draw_label,
                        rgbcolor: 'rgba(255, 255, 255, 0.1)'
                    };
                } else {
                    properties = {};
                }

                //e.feature.setValues(properties);
                e.feature.setProperties(properties);

                //$log.debug(e.feature.getProperties());
                // need to manually update the angular state, since they're not directly linked
                externalApply();
            });

            // initialize map (imageviewer)
            this.map = new ol.Map({
                renderer: 'canvas',
                target: mapContainer,
                logo: false
            });

            // set map event handlers
            this.map.on('singleclick', function(evt) {
                var click_coords = self.flipYCoord(evt.coordinate);

                if (self.draw_mode === 'navigate') {
                    self.last_click_location = click_coords;

                } else if (self.draw_mode === 'pointlist') {
                    self.last_click_location = evt.coordinate;

                } else if (self.draw_mode === 'autofill') {
                    self.last_click_location = click_coords;
                    self.autofill(click_coords);

                } else if (self.draw_mode === 'lines') {
                    self.last_click_location = evt.coordinate;
                    self.addPoint(evt.coordinate);
                }
            });

            $(this.map.getViewport()).on('mousemove', function (evt) {
                var pixel = self.map.getEventPixel(evt.originalEvent);
                self.featuresAtPoint(pixel);
            });
        };


        // Define the "instance" methods using the prototype
        // and standard prototypal inheritance.
        olViewer.prototype = {

            clearCurrentImage: function () {
                if (this.image_layer) {
                    this.map.removeLayer(this.image_layer);
                }
            },

            hasLayerAnnotations: function () {
                return this.vector_source.getFeatures().length > 0;
            },

            moveToFeature: function (feature) {
                this.map.getView().fitGeometry(
                    feature.getGeometry(),
                    this.map.getSize(),
                    {
                        padding: [120, 20, 20, 20],
                        constrainResolution: false
                    }
                );
            },

            featuresAtPoint: function (pixel) {
                var feature = this.map.forEachFeatureAtPixel(pixel, function (feature, layer) {
                    return feature;
                });
                var info = document.getElementById('objectinfo');

                if (feature) {
                    var icon = feature.get('icon');

                    if (icon) {
                        info.src = icon;
                        info.style.display = 'inline';
                    } else {
                        info.src = '/uda/static/na.jpg';
                        info.style.display = 'none';
                    }
                } else {
                    info.style.display = 'none';
                    info.src = '/uda/static/na.jpg'
                }
            },

            featureListFromAnnotation: function (annotation) {
                // $log.debug(annotation);
                var features_list = [];

                if (annotation.polygons.length > 0) {
                    var af_feature = new ol.Feature({
                        classification: annotation.classification
                    });

                    af_feature.setGeometry(new ol.geom.Polygon([annotation.polygons]));
                    features_list.push(af_feature);
                }

                if (annotation.lines.length > 0) {
                    var l_feature = new ol.Feature({
                        classification: annotation.classification
                    });

                    l_feature.setGeometry(new ol.geom.Polygon([annotation.lines]));
                    features_list.push(l_feature);
                }

                return features_list;
            },

            getFeatures: function () {
                return this.vector_source.getFeatures();
            },

            setAnnotations: function (features) {
                if (features) {
                    this.vector_source.addFeatures(features);
                }
            },

            clearLayerAnnotations : function (step) {
                this.vector_source.clear();
            },

            removeDrawInteraction: function () {
                if (this.draw_interaction) {
                    this.map.removeInteraction(this.draw_interaction);
                }
            },

            setFillParameter: function (new_fill_tolerance) {
                this.fill_tolerance = new_fill_tolerance;
            },

            setPaintParameter: function (new_paint_size) {
                this.paint_size = new_paint_size;
            },

            regenerateFill: function () {
              this.autofill(this.last_click_location);
            },

            autofill: function (click_coords) {
                var self = this;

//                var extent = this.map.getView().calculateExtent(this.map.getSize());
//                var tr = ol.extent.getTopRight(extent);
//                var tl = ol.extent.getTopLeft(extent);
//                var bl = ol.extent.getBottomLeft(extent);
                // think: if x is positive on left, subtract from total width
                // if x on right is greater than width, x = width

                var segmentURL = '/api/v1/image/' + this.current_image_id + '/segment';
                var msg = {
                    tolerance: this.fill_tolerance,
                    seed: click_coords.map(Math.round)
                };
                $http.post(segmentURL, msg).success(function (response) {

                    self.vector_source.clear();
                    var f = new ol.format.GeoJSON();

                    // translate and flip the y-coordinates
                    var coordinates = response.geometry.coordinates[0];
                    for (var j=0; j<coordinates.length; j++) {
                        coordinates[j][1] = self.flipYCoord(coordinates[j])[1];
                    }

                    var featobj = f.readFeature(response);
                    featobj.setId(0);
                    featobj.setProperties({
                        rgbcolor: 'rgba(255, 255, 255, 0.1)',
                        hexcolor: '#ff0000',
                        title : self.draw_label,
                        icon : '/uda/static/derm/images/lesion.jpg'
                    });

                    self.vector_source.addFeature(featobj);

                    // manually request an updated frame async
                    self.map.render();
                });
            },

            hasJobResult: function (results) {
                if (results.uuid == this.last_job_id) {
                    $log.debug(results.result);
                }
            },

            setDrawMode: function (draw_mode, draw_label) {
                this.draw_mode = draw_mode;
                this.draw_label = draw_label;

                $log.debug('Draw settings:', this.draw_mode, this.draw_label);

                if (draw_mode == 'navigate') {

                } else if (draw_mode == 'paintbrush') {

                } else if (draw_mode == 'autofill') {

                } else if (draw_mode == 'pointlist') {
                    this.map.addInteraction(this.draw_interaction);
                }
            },

            flipYCoord: function (coord) {
                return [
                    coord[0],
                    this.image_metadata.maxBaseY - coord[1]
                ];
            },

            loadImageWithURL: function (image_id) {
                var self = this;

                self.current_image_id = image_id;
                var tiles_url = '/api/v1/image/' + image_id + '/tiles';

                $http.get(tiles_url).success(function (metadata) {
                    self.image_metadata = metadata;

                    // OpenLayers has no apparant way to crop an image to not
                    // include the padding at the bottom/right edges (maybe it's
                    // in 'tileGrid'?); so; instead tell OpenLayers that the
                    // extent of the image actually includes the padding; it will
                    // typicallly not be visible (though perhaps we should ignore
                    // events on the extra region?)
                    metadata.maxBaseX = metadata.tileWidth * Math.pow(2, metadata.levels - 1);
                    metadata.maxBaseY = metadata.tileHeight * Math.pow(2, metadata.levels - 1);

                    var projection = new ol.proj.Projection({
                        code: 'pixel',
                        units: 'pixels',
                        //extent: [0, 0, metadata.sizeX, metadata.sizeY],
                        extent: [0, 0, metadata.maxBaseX, metadata.maxBaseY],
                        //worldExtent: [0, 0, metadata.sizeX, metadata.sizeY],
                        worldExtent: [0, 0, metadata.maxBaseX, metadata.maxBaseY],
                        axisOrientation: 'enu',
                        global: true
                    });

                    self.image_layer = new ol.layer.Tile({
                        source: new ol.source.XYZ({
                            tileSize: [metadata.tileWidth, metadata.tileHeight],
                            url: tiles_url + '/{z}/{x}/{y}',
                            crossOrigin: 'use-credentials',
                            maxZoom: metadata.levels,
                            wrapX: false,
                            projection: projection
                            //tileGrid: new ol.tilegrid.TileGrid({
                            //    extent: [0.0, 0.0, metadata.sizeX, metadata.sizeY],
                            //    //tileSize: [metadata.tileWidth, metadata.tileHeight]
                            //})
                        }),
                        preload: 1
                        //extent: [0, 0, metadata.sizeX, metadata.sizeY]
                    });

                    var view = new ol.View({
                        minZoom: 0,
                        maxZoom: metadata.levels,
                        center: self.flipYCoord([
                            metadata.sizeX / 2,
                            metadata.sizeY / 2
                        ]),
                        zoom: 2,
                        projection: projection
                    });
                    self.map.addLayer(self.image_layer);
                    self.map.addLayer(self.vector_layer);
                    self.map.setView(view);
                });
            }
        };
        return olViewer;
    }
);
