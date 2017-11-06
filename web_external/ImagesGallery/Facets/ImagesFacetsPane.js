import _ from 'underscore';

import View from '../../view';

import ImagesFacetsPaneTemplate from './imagesFacetsPane.pug';
import './imagesFacetsPane.styl';

const ImagesFacetsPane = View.extend({
    /**
     * @param {ImagesFacetCollection} settings.completeFacets
     * @param {ImagesFacetCollection} settings.filteredFacets
     * @param {ImagesFilter} settings.filters
     */
    initialize: function (settings) {
        this.completeFacets = settings.completeFacets;
        this.filteredFacets = settings.filteredFacets;
        this.filters = settings.filters;

        // TODO: Use the more general 'update' event, once Girder's version of Backbone is upgraded
        // TODO: ensure this fires when facets are modified in-place
        this.listenTo(this.completeFacets, 'sync', this.render);

        this._facetViews = [];
    },

    render: function () {
        _.each(this.facetViews, (facetView) => {
            facetView.destroy();
        });
        this._facetViews = [];
        this.$el.empty();

        this.$el.html(ImagesFacetsPaneTemplate({
            filterHexColors: [
                '00ABFF', // for hover on check buttons
                'CCCCCC' // for buttons with ".disabled" (possibly not used)
            ]
        }));

        this._createFacetView('meta.clinical.diagnosis')
            .$el.insertBefore(this.$('.isic-images-facets-clinical'));
        this.completeFacets.forEach((completeFacet) => {
            const facetId = completeFacet.id;

            let headerEl = null;
            // TODO: Use String.startswith and a ES6 polyfill
            if (facetId.indexOf('meta.clinical') !== -1) {
                if (facetId === 'meta.clinical.diagnosis') {
                    // Special case
                    return;
                }
                headerEl = this.$('.isic-images-facets-clinical');
            } else if (facetId.indexOf('meta.acquisition') !== -1) {
                headerEl = this.$('.isic-images-facets-acquisition');
            } else {
                headerEl = this.$('.isic-images-facets-database');
            }

            this._createFacetView(facetId)
                .$el.appendTo(headerEl);
        });

        _.each(this._facetViews, (facetView) => {
            facetView.render();
        });

        return this;
    },

    _createFacetView: function (facetId) {
        const completeFacet = this.completeFacets.get(facetId);
        const FacetView = completeFacet.schema().FacetView;
        const facetView = new FacetView({
            completeFacet: completeFacet,
            filteredFacet: this.filteredFacets.get(facetId),
            filter: this.filters.facetFilter(facetId),
            parentView: this
        });
        this._facetViews.push(facetView);
        return facetView;
    }
});

export default ImagesFacetsPane;
