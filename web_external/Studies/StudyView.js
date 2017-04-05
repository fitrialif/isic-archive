isic.views.StudyView = isic.View.extend({
    events: {
        'click .isic-study-add-user-button': function () {
            if (!this.studyAddUserWidget) {
                this.studyAddUserWidget = new isic.views.StudyAddUserWidget({
                    el: $('#g-dialog-container'),
                    study: this.model,
                    parentView: this
                }).on('g:saved', function () {
                    this.model.once('g:fetched', function () {
                        this.render();
                    }, this).fetch();
                }, this);
            }
            this.studyAddUserWidget.render();
        },

        'click .isic-study-remove-user-button': function (event) {
            var target = $(event.currentTarget);
            var userId = target.closest('[data-user-id]').data('userId');
            // TODO: StudyModel.users() should be cached instead of re-created
            var user = this.model.users().get(userId);
            this.confirmRemoveUser(user);
        },

        'click .isic-study-destroy-button': 'confirmDestroy'
    },

    /**
     * @param {isic.models.StudyModel} settings.model
     * @param {boolean} settings.canAdminStudy - Whether the current user can admin the study.
     */
    initialize: function (settings) {
        this.canAdminStudy = settings.canAdminStudy;

        // Display loading indicator
        this.loadingAnimation = new girder.views.LoadingAnimation({
            el: this.el,
            parentView: this
        }).render();

        this.model.once('g:fetched', function () {
            // Don't "this.loadingAnimation.destroy()", as it will unbind all events on "this.el"
            delete this.loadingAnimation;

            this.render();
        }, this).fetch();
    },

    render: function () {
        this.$el.html(isic.templates.studyPage({
            canAdminStudy: this.canAdminStudy,
            study: this.model,
            formatDate: this.formatDate
        }));

        this.$('.isic-tooltip').tooltip({
            delay: 100
        });

        return this;
    },

    confirmRemoveUser: function (user) {
        girder.confirm({
            text: '<h4>Permanently remove <b>"' + _.escape(user.name()) + '"</b> from study?</h4>',
            escapedHtml: true,
            confirmCallback: _.bind(function () {
                // Ensure dialog is hidden before continuing. Otherwise,
                // when destroy() displays its modal alert dialog,
                // the Bootstrap-created element with class "modal-backdrop"
                // is erroneously not removed.
                $('#g-dialog-container').on('hidden.bs.modal', _.bind(this.removeUser, this, user));
            }, this)
        });
    },

    removeUser: function (user) {
        this.model
            .removeUser(user)
            .done(_.bind(function () {
                this.model.once('g:fetched', function () {
                    // TODO: re-render this via model events instead
                    this.render();
                }, this).fetch();
                isic.showAlertDialog({
                    text: '<h4>Annotator <b>"' + _.escape(user.name()) + '"</b> deleted</h4>',
                    escapedHtml: true
                });
            }, this))
            .fail(function (resp) {
                isic.showAlertDialog({
                    text: '<h4>Error deleting annotator</h4><br>' + _.escape(resp.responseJSON.message),
                    escapedHtml: true
                });
            });
    },

    confirmDestroy: function () {
        girder.confirm({
            text: '<h4>Permanently delete <b>"' + _.escape(this.model.name()) + '"</b> study?</h4>',
            escapedHtml: true,
            confirmCallback: _.bind(function () {
                // Ensure dialog is hidden before continuing. Otherwise,
                // when destroy() displays its modal alert dialog,
                // the Bootstrap-created element with class "modal-backdrop"
                // is erroneously not removed.
                $('#g-dialog-container').on('hidden.bs.modal', _.bind(this.destroyModel, this));
            }, this)
        });
    },

    destroyModel: function () {
        this.model.destroy({
            success: function (model, resp, options) {
                isic.showAlertDialog({
                    text: '<h4>Study <b>"' + _.escape(model.name()) + '"</b> deleted</h4>',
                    escapedHtml: true
                });
            },
            error: function (model, resp, options) {
                isic.showAlertDialog({
                    text: '<h4>Error deleting study</h4><br>' + _.escape(resp.responseJSON.message),
                    escapedHtml: true
                });
            }
        });
    }
});
