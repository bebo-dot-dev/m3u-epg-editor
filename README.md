# m3u-epg-editor
An m3u / epg file optimizer script written in python

m3u-epg-editor enables download of m3u / epg files from a remote web server and introduces features to trim / optimize these files to a set of wanted channel groups along with the ability to sort / reorder channels

These features can prove useful where:

1. You have an underpowered device where SPMC / KODI / some other app running on that device is struggling to download and process very large m3u / epg files
2. Your service provider supplies you with a url that returns an m3u file containing both live TV channels and VOD content in that one file and you want to filter it to contain only live TV channels
3. You just want to achieve a filtered list and an improved custom sort order of TV channels

This script has been tested with the following IPTV providers:

1. **VaderStreams**
2. **FabIPTV**

It is worth noting that VaderStreams do support a unique feature to enable filtering groups within their m3u in the HTTP GET request/response via a `filterCategory` query string parameter. However there are some issues that are common to all IPTV service providers where there is no obvious, easy or free solution:

1. There is no method to remove specific channels within categories / groups
2. There is no method to re-order / sort channels within categories / groups to achieve a desired custom sort order
3. There is no method to reduce the volume of data within the epg to include only those channels that are required
4. There is no method to reduce the time window of data within the epg

There are commercially available online services that can solve these problems for a monthly / yearly subscription free.

m3u-epg-editor solves these problems for free on your own network / computer(s).

***

#### dependencies:
`python`

The recommended python version is v2.7.14. Python v3 is **not** currently supported. Python installers can be downloaded from the official python website: [https://www.python.org/downloads/](https://www.python.org/downloads/). In linux, python can also be installed from a package repository with a package manager i.e. `apt`, `yum` etc or a software manager i.e. synaptic

#### python modules used by this script:
```
import sys
import os
import argparse
import ast
import requests
import re
import shutil
import gzip
from xml.etree.cElementTree import Element, SubElement, parse, ElementTree
import datetime
import dateutil.parser
from urllib import url2pathname
```

#### installing requests:
The python `requests` module is not installed by default when python is installed. This script has a dependency on the requests module to enable HTTP requests to be performed; the requests module needs to be installed for this script to work.

If the requests module is not installed you'll see a runtime error that looks something like this when you attempt to run the script:

`ImportError: no module named requests`.

The requests module can be installed with pip i.e. `pip install requests`
***

#### command line options:
```
$ python ./m3u-epg-editor.py --help
usage: m3u-epg-editor.py [-h] [--m3uurl [M3UURL]] [--epgurl [EPGURL]]
                         [--groups [GROUPS]] [--channels [CHANNELS]]
                         [--range [RANGE]] [--sortchannels [SORTCHANNELS]]
                         [--outdirectory [OUTDIRECTORY]]
                         [--outfilename [OUTFILENAME]]

download and optimize m3u/epg files retrieved from a remote web server

optional arguments:
  -h, --help            show this help message and exit
  --m3uurl [M3UURL], -m [M3UURL]
                        The url to pull the m3u file from
  --epgurl [EPGURL], -e [EPGURL]
                        The url to pull the epg file from
  --groups [GROUPS], -g [GROUPS]
                        Channel groups in the m3u to keep
  --channels [CHANNELS], -c [CHANNELS]
                        Individual channels in the m3u to discard
  --range [RANGE], -r [RANGE]
                        An optional range window (in hours) to consider when adding programmes to the epg
  --sortchannels [SORTCHANNELS], -s [SORTCHANNELS]
                        The optional desired sort order for channels in the generated m3u
  --outdirectory [OUTDIRECTORY], -d [OUTDIRECTORY]
                        The output folder where retrieved and generated file are to be stored
  --outfilename [OUTFILENAME], -f [OUTFILENAME]
                        The output filename for the generated files
```

#### sample usage calls (urls intentionally incomplete):
**VaderStreams:**
```
$ python ./m3u-epg-editor.py -m="http://xxx.xxx.xxx/vget?username=<USERNAME>&password=<PASSWORD>&format=ts" -e="http://xxx.xxx/p2.xml.gz" -g="'sports','premium movies'" -c="'willow hd','bein sports espanol hd'" -r=12 -d="/home/target_directory" -f="output_file"
```
**FabIPTV:**
```
$ python ./m3u-epg-editor.py -m="http://xxx.xxx:8080/get.php?username=<USERNAME>&password=<PASSWORD>&type=m3u_plus&output=ts" -e="http://xxx.xxx:8080/xmltv.php?username=<USERNAME>&password=<PASSWORD>" -g="'uk + 1 channels','uk bt sport','uk documentaries','uk entertainment','uk movies','uk other sports','uk sky sports'" -c="'dave hd'" -r=12 -d="/home/target_directory" -f="output_file"
```
***

#### files created by this script:

![files](./screenshots/files-screenshot-2018-01-23-21.57.28.png)

Each time this script is run, the following files will be created / overwritten in the specified `--outdirectory / -d` path:

* **original.m3u**

   This is the original unmodified m3u file downloaded from the specified `--m3uurl / -m` remote server
   
* **original.channels.txt**

   This is a raw text file log that contains an unfiltered list of all channel names from the original m3u
   
* **original.gz**

   This is the original unmodified epg gzip file downloaded from the specified `--epgurl / -e` remote server
   
* **original.xml**

   This is the original unmodified epg xml file extracted from the original epg gzip file 
   
* **[--outfilename].m3u**

   This is the new rewritten m3u file created from the original m3u file. This will contain all of the channels that you've decided to keep. Channels are optionally sorted according to the sort order specified in `--sortchannels / -s`
   
* **[--outfilename].channels.txt**

   This is basically a raw text file log containing the list of channel names from the original m3u that you've decided to keep. This can be useful for constructing a desired `--sortchannels / -s` sort order.
   
* **[--outfilename].xml**

   This is the new rewritten epg file created from the original epg file that contains epg data for all of the channels that you've decided to keep. If `--range / -r` was specified, epg data will be filtered to only include entries that fall within the range window of `range_start <= programme_start <= range_end`
   
* **no_epg_channels.txt**

   This is a log of any channels that you decided to keep that were subsequently found to have no epg data available. This can be useful to help to construct a list of `--channels / -c` channels to exclude if i.e. you only want to keep those channels where epg data is available
