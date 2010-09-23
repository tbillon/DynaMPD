#!/usr/bin/env python
# -*- coding: utf-8 -*-

#
# DO WHAT THE FUCK YOU WANT TO PUBLIC LICENSE
#                     Version 2, December 2004
#
#  Copyright (C) 2009 ubitux
#  Everyone is permitted to copy and distribute verbatim or modified
#  copies of this license document, and changing it is allowed as long
#  as the name is changed.
#
#             DO WHAT THE FUCK YOU WANT TO PUBLIC LICENSE
#    TERMS AND CONDITIONS FOR COPYING, DISTRIBUTION AND MODIFICATION
#
#   0. You just DO WHAT THE FUCK YOU WANT TO.
#

import mpd, time, urllib, xml.dom.minidom, re, random
from xml.parsers.expat import ExpatError as ParseError

__author__ = 'ubitux and Amak'
__version__ = '1.0.0'

class DynaMPD:

    _api_key = 'b25b959554ed76058ac220b7b2e0a026'
    _api_root_url = 'http://ws.audioscrobbler.com/2.0/'
    _sim_scores = {'title': 4, 'artist': 1}

    def __init__(self, mpd_client):
        self.mpd_client = mpd_client
        self.max_selection_len = mpd_client.cfg.msongs

    def get_a_selection(self, playing_artist, playing_track):

        def sel_ok(selection):
            self._log('')
            return selection

        def split_artists(artists):
            return [artists] + [a.strip() for a in re.split(r'(?i),|feat[^ ]*|&', artists)]

        playlist = self.mpd_client.playlist()
        selection = []

        self._log(':: Search similar track [%s - %s]' % (playing_artist, playing_track))

        doc = self._api_request({'method': 'track.getsimilar', 'artist': playing_artist, 'track': self._cleanup_track_title(playing_track)})
        for node in doc.getElementsByTagName('track'):

            title, artist = None, None
            for name in node.getElementsByTagName('name'):
                if name.parentNode == node:
                    title = name.firstChild.data.encode('utf-8', 'ignore')
                else:
                    artist = name.firstChild.data.encode('utf-8', 'ignore')
            if None in (title, artist):
                continue

            songs = self.mpd_client.search('artist', artist, 'title', title)
            if self._add_one_song_to_selection(songs, playlist, selection) >= self.max_selection_len:
                return sel_ok(selection)

        for sub_artist in split_artists(playing_artist):
            doc = self._api_request({'method': 'artist.getsimilar', 'artist': sub_artist})
            for node in doc.getElementsByTagName('artist'):
                artist = node.getElementsByTagName('name')[0].firstChild.data.encode('utf-8', 'ignore')

                if not self.mpd_client.search('artist', artist):
                    self._log('No artist matching [%s] in database' % artist)
                    continue

                doc_toptracks = self._api_request({'method': 'artist.getTopTracks', 'artist': artist})
                track = doc_toptracks.getElementsByTagName('track')[0]
                title = track.getElementsByTagName('name')[0].firstChild.data.encode('utf-8', 'ignore')
                songs = self.mpd_client.search('artist', artist, 'title', title)
                if self._add_one_song_to_selection(songs, playlist, selection) >= self.max_selection_len:
                    return sel_ok(selection)

        return sel_ok(selection)

    def _cleanup_track_title(self, title):
        return re.sub(r'\([^)]*\)', '', title).strip().lower()

    def _get_similitude_score(self, artist, title):
        artist, title = artist.lower(), self._cleanup_track_title(title)
        plinfo = self.mpd_client.playlistinfo()
        sim = 0
        for song in plinfo:
            if not 'artist' in song or not 'title' in song:
                continue
            tmp_artist = song['artist'].lower()
            tmp_title = self._cleanup_track_title(song['title'])
            if tmp_artist in artist or artist in tmp_artist:
                sim += self._sim_scores['artist']
            if title in tmp_title or tmp_title in title:
                sim += self._sim_scores['title']
        return sim

    def _add_one_song_to_selection(self, songs, playlist, selection):
        sel_len = len(selection)
        if not songs:
            return sel_len
        for song in songs:
            artist = song.get('artist')
            title = song.get('title')
            fname = song['file']
            if not artist or not title or fname in playlist + selection:
                continue
            score = self._get_similitude_score(artist, title)
            min_score = sum(self._sim_scores.values())
            max_score = min_score * 3
            if score > random.randint(min_score, max_score):
                continue
            self._log('    → %s' % fname)
            selection.append(fname)
            return sel_len + 1
        return sel_len

    def _api_request(self, data):
        url = self._api_root_url + '?api_key=' + self._api_key + '&' + urllib.urlencode(data)
        self._log('   [LastFM] request: %s | url: %s' % (data['method'], url))
        return xml.dom.minidom.parse(urllib.urlopen(url))

    def _log(self, msg):
        if self.mpd_client.cfg.verbose:
            print msg

class Core(mpd.MPDClient):

    _config_file = '~/.config/dynampd.conf'
    cfg = ()

    def __init__(self):

        def getopts_from_file():
            import os, ConfigParser

            c = type('',(),{})
            config = ConfigParser.SafeConfigParser({'host'      : 'localhost',
                                                    'max_songs' : '3',
                                                    'port'      : '6600',
                                                    'password'  : None,
                                                    'verbose'   : 'no',
                                                    'wait'      : '20'})
            config.read(os.path.expanduser(self._config_file))
            c.host      = config.get('DEFAULT', 'host')
            c.password  = config.get('DEFAULT', 'password')
            c.port      = config.getint('DEFAULT', 'port')
            c.verbose   = config.getboolean('DEFAULT', 'verbose')
            c.msongs    = config.getint('DEFAULT', 'max_songs')
            c.wait      = config.getint('DEFAULT', 'wait')
            return c

        def getopts(c):
            import optparse

            parser = optparse.OptionParser()
            parser.add_option('-a', '--host', dest='host', help='MPD host', default=c.host)
            parser.add_option('-n', '--password', dest='password', help='MPD password', default=c.password)
            parser.add_option('-p', '--port', dest='port', type='int', help='MPD port', default=c.port)
            parser.add_option('-q', '--quiet', dest='verbose', action="store_false", help='Quiet mode', default=(not c.verbose))
            parser.add_option('-m', '--max-songs', dest='max_songs', type='int', help='Maximum songs to append each time', default=c.msong)
            parser.add_option('-w', '--wait', dest='wait', type='int', help='Percent of current song length to wait before requesting new songs', default=c.wait)
            (opts, _) = parser.parse_args()
            return opts

        mpd.MPDClient.__init__(self)
        cfg = getopts_from_file()
        cfg = getopts(cfg)

        self.connect(cfg.host, cfg.port)
        if cfg.password:
            self.password(cfg.password)

    def run(self):

        def is_worth_listening(elapsed_time, total_time):
            return (total_time - elapsed_time) < int(total_time * (100 - cfg.wait) / 100.)

        prev = (None, None)
        dynampd = DynaMPD(self)
        try:
            while True:
                state = self.status()['state']
                if state == 'play':
                    elapsed = self.status()['time'].split(':')[0]
                    currentsong = self.currentsong()
                    (artist, title, duration) = (currentsong.get('artist'), currentsong.get('title'), currentsong.get('time').split(":")[0])
                    if artist and title and prev != (artist, title) and is_worth_listening(int(elapsed), int(duration)):
                        prev = (artist, title)
                        try:
                            for fname in dynampd.get_a_selection(artist, title):
                                self.add(fname)
                        except ParseError:
                            prev = (None, None)
                            print 'Error: unable to parse Last.FM DOM. retry in 5 seconds'
                time.sleep(5)
        except KeyboardInterrupt:
            if cfg.verbose:
                print 'Dynampd %s is now quitting...' % (__version__ )

if __name__ == '__main__':
    Core().run()
