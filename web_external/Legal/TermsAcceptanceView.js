isic.views.TermsAcceptanceView = isic.View.extend({
    events: {
        'click #isic-terms-accept': function (event) {
            if (girder.currentUser) {
                girder.currentUser.setAcceptTerms(function () {
                    // Refresh page
                    Backbone.history.loadUrl();
                });
                // TODO: disable buttons while request is pending
            } else {
                window.sessionStorage.setItem('acceptTerms', 'true');
                Backbone.history.loadUrl();
            }
        },
        'click #isic-terms-reject': function (event) {
            girder.events.trigger('g:navigateTo', isic.views.FrontPageView);
        }
    },
    initialize: function () {
        this.render();
    },

    render: function () {
        this.$el.html(isic.templates.termsAcceptancePage({
            documentsRoot: girder.staticRoot + '/built/plugins/isic_archive/extra/documents'
        }));
        return this;
    }
}, {
    // Static methods
    hasAcceptedTerms: function () {
        if (girder.currentUser) {
            return girder.currentUser.canAcceptTerms();
        } else {
            return window.sessionStorage.getItem('acceptTerms') === 'true';
        }
    }
});

isic.router.route('termsAcceptance', 'termsAcceptance', function () {
    girder.events.trigger('g:navigateTo', isic.views.TermsAcceptanceView);
});
