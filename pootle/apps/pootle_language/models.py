#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2009-2013 Zuza Software Foundation
# Copyright 2013 Evernote Corporation
#
# This file is part of Pootle.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, see <http://www.gnu.org/licenses/>.

from django.conf import settings
from django.core.cache import cache
from django.core.urlresolvers import reverse
from django.db import models
from django.utils.translation import ugettext_lazy as _

from pootle.core.managers import RelatedManager
from pootle.core.mixins import TreeItem
from pootle.core.url_helpers import get_editor_filter
from pootle.i18n.gettext import tr_lang, language_dir
from pootle_misc.baseurl import l


# FIXME: Generate key dynamically
CACHE_KEY = 'pootle-languages'


class LanguageManager(RelatedManager):

    def get_by_natural_key(self, code):
        return self.get(code=code)


class LiveLanguageManager(models.Manager):
    """Manager that only considers `live` languages.

    A live language is any language other than the special `Templates`
    language that have any project with translatable files and is not a
    source language.

    Note that this doesn't inherit from :cls:`RelatedManager`.
    """
    def get_query_set(self):
        return super(LiveLanguageManager, self).get_query_set().filter(
                ~models.Q(code='templates'),
                translationproject__isnull=False,
                project__isnull=True,
            ).distinct()

    def cached(self):
        languages = cache.get(CACHE_KEY)
        if not languages:
            languages = self.all()
            cache.set(CACHE_KEY, languages, settings.OBJECT_CACHE_TIMEOUT)

        return languages


class Language(models.Model, TreeItem):

    code_help_text = _('ISO 639 language code for the language, possibly '
            'followed by an underscore (_) and an ISO 3166 country code. '
            '<a href="http://www.w3.org/International/articles/language-tags/">'
            'More information</a>')
    code = models.CharField(max_length=50, null=False, unique=True,
            db_index=True, verbose_name=_("Code"), help_text=code_help_text)
    fullname = models.CharField(max_length=255, null=False,
            verbose_name=_("Full Name"))

    specialchars_help_text = _('Enter any special characters that users '
            'might find difficult to type')
    specialchars = models.CharField(max_length=255, blank=True,
            verbose_name=_("Special Characters"),
            help_text=specialchars_help_text)

    plurals_help_text = _('For more information, visit '
            '<a href="http://translate.sourceforge.net/wiki/l10n/pluralforms">'
            'our wiki page</a> on plural forms.')
    nplural_choices = (
            (0, _('Unknown')), (1, 1), (2, 2), (3, 3), (4, 4), (5, 5), (6, 6)
    )
    nplurals = models.SmallIntegerField(default=0, choices=nplural_choices,
            verbose_name=_("Number of Plurals"), help_text=plurals_help_text)
    pluralequation = models.CharField(max_length=255, blank=True,
            verbose_name=_("Plural Equation"), help_text=plurals_help_text)

    directory = models.OneToOneField('pootle_app.Directory', db_index=True,
            editable=False)

    pootle_path = property(lambda self: '/%s/' % self.code)

    objects = LanguageManager()
    live = LiveLanguageManager()

    class Meta:
        ordering = ['code']
        db_table = 'pootle_app_language'

    def natural_key(self):
        return (self.code,)
    natural_key.dependencies = ['pootle_app.Directory']

    @property
    def name(self):
        """localized fullname"""
        return tr_lang(self.fullname)

    @property
    def direction(self):
        """Return the language direction."""
        return language_dir(self.code)

    def __unicode__(self):
        return u"%s - %s" % (self.name, self.code)

    def __init__(self, *args, **kwargs):
        super(Language, self).__init__(*args, **kwargs)

    def __repr__(self):
        return u'<%s: %s>' % (self.__class__.__name__, self.fullname)

    def save(self, *args, **kwargs):
        # create corresponding directory object
        from pootle_app.models.directory import Directory
        self.directory = Directory.objects.root.get_or_make_subdir(self.code)

        super(Language, self).save(*args, **kwargs)

        # FIXME: far from ideal, should cache at the manager level instead
        cache.delete(CACHE_KEY)

    def delete(self, *args, **kwargs):
        directory = self.directory
        super(Language, self).delete(*args, **kwargs)
        directory.delete()

        # FIXME: far from ideal, should cache at the manager level instead
        cache.delete(CACHE_KEY)

    def get_absolute_url(self):
        return l(self.pootle_path)

    def get_translate_url(self, **kwargs):
        return u''.join([
            reverse('pootle-language-translate', args=[self.code]),
            get_editor_filter(**kwargs),
        ])

    ### TreeItem

    def get_children(self):
        return self.translationproject_set.all()

    def get_cachekey(self):
        return self.directory.pootle_path

    ### /TreeItem

    def translated_percentage(self):
        total = max(self.get_total_wordcount(), 1)
        translated = self.get_translated_wordcount()
        return int(100.0 * translated / total)
