isic.views.ImagesFacetsPane = isic.View.extend({
    render: function () {
        if (!this.addedCollapseImage) {
            // little hack to inject the correct expander image path into the
            // stylesheet (afaik, we can't access girder.staticRoot from the
            // stylus files)
            var isicStylesheet = Array.from(document.styleSheets)
                .filter(function (sheet) {
                    return sheet.href &&
                        sheet.href.indexOf('isic_archive.app.min.css') !== -1;
                })[0];
            isicStylesheet.insertRule('#isic-images-histogramPane ' +
                '.attributeSection .header input.expander:before ' +
                '{background-image: url(' + girder.staticRoot +
                    '/built/plugins/isic_archive/extra/img/collapse.svg);}',
                0);
            this.addedCollapseImage = true;
        }

        _.each(this.facetViews, function (facetView) {
            facetView.destroy();
        }, this);
        this.$el.empty();

        this.facetViews = {};
        _.each(_.keys(isic.ENUMS.SCHEMA), function (facetName) {
            var facetView = new isic.ENUMS.SCHEMA[facetName].FacetView({
                model: this.model,
                facetName: facetName,
                parentView: this
            });

            this.facetViews[facetName] = facetView;
            this.$el.append(facetView.el);
            // Do not render until the view has been inserted into the main DOM
            facetView.render();
        }, this);

        return this;
    }
});