import events from 'girder/events';
import PluginConfigBreadcrumbWidget from 'girder/views/widgets/PluginConfigBreadcrumbWidget';
import {restRequest} from 'girder/rest';
import View from 'girder/views/View';

import ConfigViewTemplate from '../templates/configView.pug';

const ConfigView = View.extend({
    events: {
        'submit #isic-config-form': function (event) {
            event.preventDefault();
            this.$('#isic-config-error-message').empty();
            this._saveSettings([
                {
                    key: 'isic.demo_mode',
                    value: this.$('#isic-config-demo-mode').prop('checked')
                },
                {
                    key: 'isic.upload_bucket_name',
                    value: this.$('#isic-config-upload-s3-bucket-name').val().trim()
                },
                {
                    key: 'isic.upload_role_arn',
                    value: this.$('#isic-config-upload-role-arn').val().trim()
                }]);
        }
    },
    initialize: function () {
        restRequest({
            type: 'GET',
            path: 'system/setting',
            data: {
                list: JSON.stringify([
                    'isic.demo_mode',
                    'isic.upload_bucket_name',
                    'isic.upload_role_arn'
                ])
            }
        }).done((resp) => {
            this.render();
            this.$('#isic-config-demo-mode').prop(
                'checked',
                resp['isic.demo_mode']
            );
            this.$('#isic-config-upload-s3-bucket-name').val(
                resp['isic.upload_bucket_name']);
            this.$('#isic-config-upload-role-arn').val(
                resp['isic.upload_role_arn']);
        });
    },

    render: function () {
        this.$el.html(ConfigViewTemplate());
        if (!this.breadcrumb) {
            this.breadcrumb = new PluginConfigBreadcrumbWidget({
                pluginName: 'ISIC Archive',
                el: this.$('.g-config-breadcrumb-container'),
                parentView: this
            }).render();
        }
        return this;
    },

    _saveSettings: function (settings) {
        restRequest({
            type: 'PUT',
            path: 'system/setting',
            data: {
                list: JSON.stringify(settings)
            },
            error: null
        }).done(() => {
            events.trigger('g:alert', {
                icon: 'ok',
                text: 'Settings saved.',
                type: 'success',
                timeout: 4000
            });
        }).fail((resp) => {
            this.$('#isic-config-error-message').text(resp.responseJSON.message);
        });
    }
});

export default ConfigView;
