//
// Annotation study results view
//

// Model for a feature
isic.models.FeatureModel = Backbone.Model.extend({
    name: function () {
        return this.get('name');
    }
});

// Model for a feature image
isic.models.FeatureImageModel = Backbone.Model.extend({
});

// Model for a global feature result
isic.models.GlobalFeatureResultModel = Backbone.Model.extend({
    name: function () {
        return this.get('name');
    }
});

// Collection of feature models
isic.collections.FeatureCollection = Backbone.Collection.extend({
    model: isic.models.FeatureModel,

    // Update collection from an array of features of the form:
    // { 'id': id, 'name': [name1, name2, ...] }
    update: function (features) {
        var models = _.map(features, function (feature) {
            var featureId = feature['id'];
            var featureNames = feature['name'];
            var model = new isic.models.FeatureModel({
                id: featureId,
                name: featureNames.join(', ')
            });
            return model;
        });
        this.reset(models);
    }
});

// Header view for collection of images
isic.views.StudyResultsImageHeaderView = isic.View.extend({
    initialize: function (options) {
        this.study = options.study;

        this.listenTo(this.collection, 'reset', this.render);

        this.render();
    },

    render: function () {
        this.$el.html(isic.templates.studyResultsImageHeaderPage({
            hasStudy: !_.isUndefined(this.study.id),
            numImages: this.collection.models.length
        }));

        return this;
    }
});

// View for a collection of studies in a select tag
isic.views.StudyResultsSelectStudyView = isic.View.extend({
    events: {
        'change': 'studyChanged',
        'click .isic-study-results-select-study-details-button': 'showDetails'
    },

    initialize: function (options) {
        this.listenTo(this.collection, 'reset', this.render);

        this.render();
    },

    studyChanged: function () {
        this.trigger('changed', this.$('select').val());

        // Enable study details button
        this.$('.isic-study-results-select-study-details-button').removeAttr('disabled');
    },

    showDetails: function () {
        var studyId = this.$('select').val();
        if (!studyId) {
            return;
        }

        this.trigger('showStudyDetails', studyId);
    },

    render: function () {
        // Destroy previous select2
        var select = this.$('#isic-study-results-select-study-select');
        select.select2('destroy');

        this.$el.html(isic.templates.studyResultsSelectStudyPage({
            models: this.collection.models
        }));

        // Set up select box
        var placeholder = 'Select a study...';
        if (!this.collection.isEmpty()) {
            placeholder += ' (' + this.collection.length + ' available)';
        }
        select = this.$('#isic-study-results-select-study-select');
        select.select2({
            placeholder: placeholder
        });
        select.focus();

        this.$('.isic-tooltip').tooltip({
            delay: 100
        });

        return this;
    }
});

// Modal view for study details
isic.views.StudyResultsStudyDetailsView = isic.View.extend({
    render: function () {
        var hasStudy = this.model.has('name');

        this.$el.html(isic.templates.studyResultsStudyDetailPage({
            model: this.model,
            hasStudy: hasStudy
        })).girderModal(this);

        return this;
    }
});

// View for a collection of images
isic.views.StudyResultsSelectImageView = isic.View.extend({
    events: {
        'click .isic-study-results-select-image-image-container': 'imageSelected'
    },

    initialize: function (options) {
        this.listenTo(this.collection, 'reset', this.render);

        this.render();
    },

    imageSelected: function (event) {
        event.preventDefault();

        // currentTarget is the element that the event has bubbled up to
        var target = $(event.currentTarget);

        this.$('.isic-study-results-select-image-image-container').removeClass('active');
        target.addClass('active');

        this.trigger('changed', target.data('imageId'));
    },

    render: function () {
        this.$el.html(isic.templates.studyResultsSelectImagePage({
            models: this.collection.models,
            apiRoot: girder.apiRoot
        }));

        return this;
    }
});

// View for a collection of users in a select tag
isic.views.StudyResultsSelectUsersView = isic.View.extend({
    events: {
        'change': 'userChanged'
    },

    initialize: function (options) {
        this.listenTo(this.collection, 'reset', this.render);

        this.render();
    },

    userChanged: function () {
        this.trigger('changed', this.$('select').val());
    },

    render: function () {
        // Destroy previous select2
        var select = this.$('#isic-study-results-select-users-select');
        select.select2('destroy');

        this.$el.html(isic.templates.studyResultsSelectUsersPage({
            models: this.collection.models
        }));

        // Set up select box
        var placeholder = 'No users available';
        if (!this.collection.isEmpty()) {
            placeholder = 'Select a user... (' + this.collection.length + ' available)';
        }
        select = this.$('#isic-study-results-select-users-select');
        select.select2({
            placeholder: placeholder
        });

        return this;
    }
});

// View for a collection of local features in a select tag
isic.views.StudyResultsSelectLocalFeaturesView = isic.View.extend({
    events: {
        'change': 'featureChanged'
    },

    initialize: function (options) {
        this.featureAnnotated = options.featureAnnotated;

        this.listenTo(this.collection, 'reset', this.render);

        this.render();
    },

    featureChanged: function () {
        this.trigger('changed', this.$('select').val());
    },

    render: function () {
        // Destroy previous select2
        var select = this.$('#isic-study-results-select-local-features-select');
        select.select2('destroy');

        // Create local collection of those features that are annotated
        var collection = this.collection.clone();
        collection.reset(collection.filter(_.bind(function (model) {
            return this.featureAnnotated(model.id);
        }, this)));

        this.$el.html(isic.templates.studyResultsSelectLocalFeaturesPage({
            models: collection.models
        }));

        // Set up select box
        var placeholder = 'No features available';
        if (!collection.isEmpty()) {
            placeholder = 'Select a feature... (' + collection.length + ' available)';
        }
        select = this.$('#isic-study-results-select-local-features-select');
        select.select2({
            placeholder: placeholder
        });

        return this;
    }
});

// Collection of global feature result models
isic.collections.GlobalFeatureResultCollection = Backbone.Collection.extend({
    model: isic.models.GlobalFeatureResultModel,

    // Update collection from annotation object and feature list
    update: function (annotations, features) {
        var models = _.map(features, function (feature) {
            var featureId = feature['id'];
            var featureNames = feature['name'];
            var model = new isic.models.GlobalFeatureResultModel({
                id: featureId,
                name: featureNames.join(', ')
            });
            if (annotations && _.has(annotations, featureId)) {
                var featureOptions = _.indexBy(feature['options'], 'id');
                var resultId = annotations[featureId];
                var resultName = featureOptions[resultId]['name'];
                model.set('resultId', resultId);
                model.set('resultName', resultName);
            }
            return model;
        });
        this.reset(models);
    }
});

// View for a global feature table
isic.views.StudyResultsGlobalFeaturesTableView = isic.View.extend({
    initialize: function (settings) {
        this.listenTo(this.collection, 'reset', this.render);
    },

    render: function () {
        this.$el.html(isic.templates.studyResultsGlobalFeaturesTable({
            features: this.collection.models
        }));

        return this;
    }
});

// View for the annotation results of global features in a featureset
isic.views.StudyResultsGlobalFeaturesView = isic.View.extend({
    initialize: function (settings) {
        this.annotation = settings.annotation;
        this.featureset = settings.featureset;

        this.results = new isic.collections.GlobalFeatureResultCollection();
        this.listenTo(this.featureset, 'change', this.render);
        this.listenTo(this.featureset, 'change', this.updateResults);
        this.listenTo(this.annotation, 'change', this.updateResults);

        this.tableView = new isic.views.StudyResultsGlobalFeaturesTableView({
            collection: this.results,
            parentView: this
        });

        this.updateResults();
        this.render();
    },

    render: function () {
        this.$el.html(isic.templates.studyResultsGlobalFeaturesPage({
            hasGlobalFeatures: !_.isEmpty(this.featureset.get('globalFeatures')),
            featureset: this.featureset
        }));

        this.tableView.setElement(
            this.$('#isic-study-results-global-features-table')).render();

        return this;
    },

    updateResults: function () {
        this.results.update(
            this.annotation.get('annotations'),
            this.featureset.get('globalFeatures')
        );
    }
});

// View for a local feature image defined by an annotation and local feature
isic.views.StudyResultsFeatureImageView = isic.View.extend({
    initialize: function (settings) {
        this.listenTo(this.model, 'change', this.render);
    },

    setVisible: function (visible) {
        if (visible) {
            this.$el.removeClass('hidden');
        } else {
            this.$el.addClass('hidden');
        }
    },

    render: function () {
        var featureId = this.model.get('featureId');
        var annotationId = this.model.get('annotationId');
        var imageUrl = null;
        if (featureId && annotationId) {
            imageUrl = [
                girder.apiRoot,
                'annotation', annotationId,
                'render?contentDisposition=inline&featureId='
            ].join('/') + encodeURIComponent(featureId);
        }

        this.$el.html(isic.templates.studyResultsFeatureImagePage({
            imageUrl: imageUrl
        }));

        return this;
    }
});

// View to allow selecting a local feature from a featureset and to display an
// image showing the annotation for the feature
isic.views.StudyResultsLocalFeaturesView = isic.View.extend({
    initialize: function (settings) {
        this.annotation = settings.annotation;
        this.featureset = settings.featureset;
        this.featureImageModel = settings.featureImageModel;
        this.features = new isic.collections.FeatureCollection();

        this.listenTo(this.featureset, 'change', this.featuresetChanged);
        this.listenTo(this.annotation, 'change', this.annotationChanged);

        this.selectFeatureView = new isic.views.StudyResultsSelectLocalFeaturesView({
            collection: this.features,
            featureAnnotated: _.bind(this.featureAnnotated, this),
            parentView: this
        });

        this.listenTo(this.selectFeatureView, 'changed', this.featureChanged);
    },

    featureChanged: function (featureId) {
        this.featureId = featureId;
        this.updateFeatureImageModel();
    },

    updateFeatureImageModel: function () {
        this.featureImageModel.set({
            featureId: this.featureId,
            annotationId: this.featureAnnotated(this.featureId) ? this.annotation.id : null
        });
    },

    render: function () {
        this.$el.html(isic.templates.studyResultsLocalFeaturesPage({
            hasLocalFeatures: !_.isEmpty(this.featureset.get('localFeatures')),
            featureset: this.featureset
        }));

        this.selectFeatureView.setElement(
            this.$('#isic-study-results-select-local-feature-container')).render();

        return this;
    },

    updateFeatureCollection: function () {
        delete this.featureId;

        this.features.update(this.featureset.get('localFeatures'));
    },

    featuresetChanged: function () {
        this.updateFeatureCollection();
        this.render();
    },

    annotationChanged: function () {
        this.featureId = null;
        this.updateFeatureImageModel();
        this.render();
    },

    featureAnnotated: function (featureId) {
        if (!featureId || !this.annotation.has('annotations')) {
            return false;
        }
        var annotations = this.annotation.get('annotations');
        return _.has(annotations, featureId);
    }
});

// View for an image
isic.views.StudyResultsImageView = isic.View.extend({
    setVisible: function (visible) {
        if (visible) {
            this.$el.removeClass('hidden');

            this.imageViewerWidget.render();
        } else {
            this.$el.addClass('hidden');
        }
    },

    render: function () {
        this.$el.html(isic.templates.studyResultsImagePage({
        }));

        this.imageViewerWidget = new isic.views.ImageViewerWidget({
            el: this.$('.isic-study-results-image-preview-container'),
            model: this.model,
            parentView: this
        }).render();

        return this;
    }
});

// View for the results of an annotation study
isic.views.StudyResultsView = isic.View.extend({
    events: {
        // Update image visibility when image preview tab is activated
        'shown.bs.tab #isic-study-results-image-preview-tab': function (event) {
            this.localFeaturesImageView.setVisible(false);
            this.imageView.setVisible(true);
        },

        // Update image visibility when global features tab is activated
        'shown.bs.tab #isic-study-results-global-features-tab': function (event) {
            this.imageView.setVisible(false);
            this.localFeaturesImageView.setVisible(false);
        },

        // Update image visibility when local features tab is activated
        'shown.bs.tab #isic-study-results-local-features-tab': function (event) {
            this.imageView.setVisible(false);
            this.localFeaturesImageView.setVisible(true);
        }
    },

    initialize: function (settings) {
        this.studies = new isic.collections.StudyCollection();
        this.studies.pageLimit = Number.MAX_SAFE_INTEGER;

        this.images = new isic.collections.ImageCollection();
        this.images.pageLimit = Number.MAX_SAFE_INTEGER;

        this.users = new isic.collections.UserCollection();
        this.users.pageLimit = Number.MAX_SAFE_INTEGER;

        this.study = new isic.models.StudyModel();
        this.image = new isic.models.ImageModel();
        this.user = new girder.models.UserModel();
        this.featureset = new isic.models.FeaturesetModel();
        this.annotation = new isic.models.AnnotationModel();
        this.featureImageModel = new isic.models.FeatureImageModel();

        this.selectStudyView = new isic.views.StudyResultsSelectStudyView({
            collection: this.studies,
            parentView: this
        });

        this.studyDetailsView = new isic.views.StudyResultsStudyDetailsView({
            model: this.study,
            parentView: this
        });

        this.imageHeaderView = new isic.views.StudyResultsImageHeaderView({
            collection: this.images,
            study: this.study,
            parentView: this
        });

        this.selectImageView = new isic.views.StudyResultsSelectImageView({
            collection: this.images,
            parentView: this
        });

        this.selectUserView = new isic.views.StudyResultsSelectUsersView({
            collection: this.users,
            parentView: this
        });

        this.globalFeaturesView = new isic.views.StudyResultsGlobalFeaturesView({
            annotation: this.annotation,
            featureset: this.featureset,
            parentView: this
        });

        this.localFeaturesView = new isic.views.StudyResultsLocalFeaturesView({
            annotation: this.annotation,
            featureset: this.featureset,
            featureImageModel: this.featureImageModel,
            parentView: this
        });

        this.imageView = new isic.views.StudyResultsImageView({
            model: this.image,
            parentView: this
        });

        this.localFeaturesImageView = new isic.views.StudyResultsFeatureImageView({
            model: this.featureImageModel,
            parentView: this
        });

        this.studies.fetch();

        this.listenTo(this.selectStudyView, 'changed', this.studyChanged);
        this.listenTo(this.selectImageView, 'changed', this.imageChanged);
        this.listenTo(this.selectUserView, 'changed', this.userChanged);

        this.listenTo(this.selectStudyView, 'showStudyDetails', this.showStudyDetails);

        this.render();
    },

    studyChanged: function (studyId) {
        this.study.clear();

        this.images.reset();
        this.users.reset();

        this.image.clear();
        this.user.clear();

        this.annotation.clear();
        this.featureset.clear();

        // Hide main and content containers
        this.setMainContainerVisible(false);
        this.setContentContainerVisible(false);

        // Fetch selected study
        this.study.set({'_id': studyId}).once('g:fetched', function () {
            // Populate images collection
            var imageModels = _.map(this.study.get('images'), function (image) {
                return new isic.models.ImageModel(image);
            });
            this.images.reset(imageModels);

            // Populate users collection
            this.users.reset(this.study.users().models);

            // Fetch featureset
            var featureset = this.study.featureset();
            featureset.once('g:fetched', function () {
                this.featureset.set(featureset.attributes);
            }, this).fetch();

            // Show main container
            this.setMainContainerVisible(true);
        }, this).fetch();
    },

    imageChanged: function (imageId) {
        this.image.set('_id', imageId);
        this.annotation.clear();
        this.fetchAnnotation();

        // Show content container
        this.setContentContainerVisible(true);
    },

    userChanged: function (userId) {
        this.user.set('_id', userId);
        this.annotation.clear();
        this.fetchAnnotation();
    },

    showStudyDetails: function (studyId) {
        this.studyDetailsView.render();
    },

    fetchAnnotation: function () {
        if (!this.image.id ||
            !this.user.id) {
            return;
        }

        var annotations = new isic.collections.AnnotationCollection();
        annotations.once('g:changed', function () {
            if (!annotations.isEmpty()) {
                // Fetch annotation detail
                this.annotation.set(annotations.first().attributes).fetch();
            }
        }, this).fetch({
            studyId: this.study.id,
            userId: this.user.id,
            imageId: this.image.id
        });
    },

    render: function () {
        this.$el.html(isic.templates.studyResultsPage());

        // Set select2 default options
        $.fn.select2.defaults.set('theme', 'bootstrap');

        this.selectStudyView.setElement(
            this.$('#isic-study-results-select-study-container')).render();
        this.studyDetailsView.setElement(
            $('#g-dialog-container'));
        this.imageHeaderView.setElement(
            this.$('#isic-study-results-select-image-header')).render();
        this.selectImageView.setElement(
            this.$('#isic-study-results-select-image-container')).render();
        this.selectUserView.setElement(
            this.$('#isic-study-results-select-user-container')).render();
        this.globalFeaturesView.setElement(
            this.$('#isic-study-results-global-features-container')).render();
        this.localFeaturesView.setElement(
            this.$('#isic-study-results-local-features-container')).render();
        this.imageView.setElement(
            this.$('#isic-study-results-image-preview-container')).render();
        this.localFeaturesImageView.setElement(
            this.$('#isic-study-results-local-features-image-container')).render();

        return this;
    },

    setElementVisible: function (element, visible) {
        if (visible) {
            element.removeClass('hidden');
        } else {
            element.addClass('hidden');
        }
    },

    setMainContainerVisible: function (visible) {
        var element = this.$('#isic-study-results-main-container');
        this.setElementVisible(element, visible);
    },

    setContentContainerVisible: function (visible) {
        this.setElementVisible(this.$('#isic-study-results-main-content'), visible);
        this.setElementVisible(this.$('#isic-study-results-select-user-container'), visible);
    }

});

isic.router.route('studyResults', 'studyResults', function () {
    var nextView = isic.views.StudyResultsView;
    if (!isic.views.TermsAcceptanceView.hasAcceptedTerms()) {
        nextView = isic.views.TermsAcceptanceView;
    }
    girder.events.trigger('g:navigateTo', nextView);
});
