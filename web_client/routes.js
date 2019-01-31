/* eslint-disable import/first */

import events from '@girder/core/events';
import {exposePluginConfig} from '@girder/core/utilities/PluginUtils';
import router from '@girder/core/router';

exposePluginConfig('isic_archive', 'plugins/isic_archive/config');

import ConfigView from './views/ConfigView';
router.route('plugins/isic_archive/config', 'isicConfig', function () {
    events.trigger('g:navigateTo', ConfigView);
});
