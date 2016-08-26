//
// Segmentations display view
//

// View for displaying an image segmentation's properties
isic.views.SegmentationDisplayView = isic.View.extend({
    initialize: function (settings) {
        this.listenTo(this.model, 'change', this.render);
        this.listenTo(this.model, 'g:fetched', this.render);

        this.render();
    },

    render: function () {
        var created = null;
        var thumbnailUrl = null;

        if (this.model.id) {
            created = girder.formatDate(this.model.get('created'), girder.DATE_SECOND);
            thumbnailUrl = [
                girder.apiRoot,
                'segmentation',
                this.model.id,
                'thumbnail?width=256'
            ].join('/');
        }

        this.$el.html(isic.templates.segmentationDisplayPage({
            segmentation: this.model,
            created: created,
            thumbnailUrl: thumbnailUrl
        }));

        return this;
    }
});

// View for selecting an image segmentation and displaying its properties
isic.views.SegmentationsDisplayView = isic.View.extend({
    events: {
        'change select': function (event) {
            var segmentationId = $(event.currentTarget).val();
            this.segmentation.set('_id', segmentationId, {silent: true});
            this.segmentation.fetch();
        }
    },

    initialize: function (settings) {
        this.image = settings.image;

        this.segmentations = new isic.collections.SegmentationCollection();
        this.segmentations.pageLimit = Number.MAX_SAFE_INTEGER;

        this.segmentation = new isic.models.SegmentationModel();

        this.segmentationDisplayView = new isic.views.SegmentationDisplayView({
            model: this.segmentation,
            parentView: this
        });

        this.listenTo(this.image, 'change', this.fetchSegmentations);
        this.listenTo(this.image, 'g:fetched', this.fetchSegmentations);

        this.render();
    },

    render: function () {
        this.$el.html(isic.templates.segmentationsDisplayPage({
            segmentations: this.segmentations.models
        }));

        this.segmentationDisplayView.setElement(
            this.$('#isic-segmentation-display-container')).render();

        return this;
    },

    fetchSegmentations: function () {
        this.segmentation.clear();

        this.render();

        if (this.image.id) {
            this.segmentations.once('g:fetched', _.bind(function () {
                this.render();
            }, this)).fetch({
                imageId: this.image.id
            });
        }
    }
});
