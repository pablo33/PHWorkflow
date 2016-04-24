#!/usr/bin/python3

''' This script moves camera file-media to a folder on our hard disk.
	it will group files in foldes due to its date of creation 
	it also manages duplicated files (same name and bytes)'''


# Module import
import sys, os, shutil, logging, datetime, time, re
from glob import glob
from gi.repository import GExiv2  # for metadata management. Dependencies: gir1.2-gexiv2   &   python-gobject
from PIL import Image  # for image conversion
import argparse  # for command line arguments
import sqlite3  # for sqlite3 Database


# Internal variables.
os.stat_float_times (False)  #  So you won't get milliseconds retrieving Stat dates; this will raise in error parsing getmtime.
moviesmedia = ['mov','avi','m4v', 'mpg', '3gp', 'mp4']
photomedia = ['jpg','jpeg','raw','png','bmp']
wantedmedia =  photomedia + moviesmedia
justif = 20  #  number of characters to justify logging info.
dupfoldername = 'duplicates'

# ================================
# =========  Utils ===============
# ================================

def itemcheck(a):
	if os.path.isfile(a):
		return 'file'
	if os.path.isdir(a):
		return 'folder'
	if os.path.islink(a):
		return 'link'
	return ""


def to2(month):
	if month > 9:
		strmonth = str(month)
	else:
		strmonth = "0" + str(month)
	return strmonth


def addslash (text):
	if text [-1] != '/':
		text += '/'
	return text

# Load user config:
# Getting user folder to place log files....
userpath = os.path.join(os.getenv('HOME'),".Photodeliver")
userfileconfig = os.path.join(userpath,"Photodelivercfg.py")
dbpath = os.path.join(userpath,"tmpDB.sqlite3")

if itemcheck (userpath) != "folder":
	os.makedirs(userpath)

if itemcheck (userfileconfig) == "file":
	print ("Loading user configuration....")
	sys.path.append(userpath)
	import Photodelivercfg
else:
	print ("There isn't an user config file: " + userfileconfig)
	# Create a new config file
	f = open(userfileconfig,"w")
	f.write ('''
# Photodeliver Config file.
# This options can be overriden by entering a command line options
# This is a python file. Be careful and see the sintaxt.

originlocation = '%(home)s/originlocation'  #  Path from where retrieve new images.
destlocation = '%(home)s/destlocation'  # 'Path to where you want to store your photos'
renamemovies = True  # This option adds a creation date in movies file-names (wich doesn't have Exif Metadata)
renamephotos = True  # This option adds a creation date in media file-names (useful if you want to modify them)
eventminpictures = 8  # Minimum number of pictures to assign a day-event
gap = 60*60*5  # Number of seconds between shots to be considered both pictures to the same event.
copymode = 'm'  # 'c' for copy or 'm' to move new files
considerdestinationitems = True  # Consider destination items in order to group media files in events.
moveexistentfiles = False  # True / False ...... True for move/reagroup or False to keep existent files at its place (Do nothing).
ignoreTrash = True  # True / False .... Ignore paths starting with '.Trash'
preservealbums = True  #  True / False  .... Do not include in fileScanning albums. An album is defined by a path that ends in _  pex.  /2015/2015 my album to preserve_/items.png 
forceassignfromfilename = True  # True / False   .... Force assign from a date found from filename if any. (This allows to override EXIF assignation if it is found).
cleaning = True  # True / False .....  Cleans empty folders (only folders that had contained photos)
storefilemetadata = True  # True means that guesed date of creation will be stored in the file-archive as EXIF metadata.
convert = True  # True / False ......  Try to convert image formats in JPG
'''%{'home':os.getenv('HOME')}
	)
	f.close()
	print ("An user config file has been created at:", userfileconfig)
	print ("Please customize by yourself before run this software again.")
	print ("This software is going to try to open with a text editor (gedit).")
	os.system ("gedit " + userfileconfig)
	exit()


# Retrieve cmd line parameters >>>>>>>>

parser = argparse.ArgumentParser()
parser.add_argument("-ol", "--originlocation",
                    help="Path from where retrieve new images.")
parser.add_argument("-dl", "--destlocation",
                    help="Path to where you want to store your photos.")
parser.add_argument("-rm", "--renamemovies", choices = [1,0], type = int,
                    help="This option adds a creation date in movies file-names (wich doesn't have Exif Metadata).")
parser.add_argument("-rp", "--renamephotos", choices = [1,0], type = int,
                    help="This option adds a creation date in media file-names (useful if you want to modify them).")
parser.add_argument("-minp", "--eventminpictures", type = int,
                    help="Minimum number of pictures to assign a day-event.")
parser.add_argument("-gap", "--gap", type = int,
                    help="Number of seconds between shots to be considered both pictures to the same event.")
parser.add_argument("-cpmode", "--copymode", choices = ['c','m'],
                    help="'c' for copy or 'm' to move new files.")
parser.add_argument("-cdi", "--considerdestinationitems", choices = [1,0], type = int,
                    help="Consider destination items in order to group media files in events.")
parser.add_argument("-mef", "--moveexistentfiles", choices = [1,0], type = int,
                    help="True for move/reagroup or False to keep existent files at its place (Do nothing)")
parser.add_argument("-it", "--ignoreTrash", choices = [1,0], type = int,
                    help="Ignore paths starting with '.Trash'")
parser.add_argument("-pa", "--preservealbums", choices = [1,0], type = int,
                    help="Do not include in fileScanning albums. An album is defined by a path that ends in _  pex.  /2015/2015 my album to preserve_/items.png ")
parser.add_argument("-faff", "--forceassignfromfilename", choices = [1,0], type = int,
                    help="Force assign from a date found in filename (if there is some). (This allows to overwrite EXIF assignation if it is found).")
parser.add_argument("-clean", "--cleaning", choices = [1,0], type = int,
                    help="Cleans empty folders (only folders that had contained photos)")
parser.add_argument("-sfm", "--storefilemetadata", choices = [1,0], type = int,
                    help="Store the guesed date in the filename as Exif data.")
parser.add_argument("-conv", "--convert", choices = [1,0], type = int,
                    help="Convert image format to JPG file")
parser.add_argument("-sc", "--showconfig", action="store_true",
                    help="Show running parameters, args parameters, config file parameters & exit")
parser.add_argument("-test", "--dummy", action="store_true",
                    help="Do not perform any file movements. Play on dummy mode.")


args = parser.parse_args()
parametersdyct = {}

# Getting variables, override config file with args.
if args.originlocation == None:
	originlocation =  Photodelivercfg.originlocation
else:
	originlocation = args.originlocation
parametersdyct["originlocation"] = originlocation


if args.destlocation == None:
	destlocation =  Photodelivercfg.destlocation
else:
	destlocation = args.destlocation
parametersdyct["destlocation"] = destlocation


if args.renamemovies == None:
	renamemovies = Photodelivercfg.renamemovies 
else:
	renamemovies = [False,True][args.renamemovies]
parametersdyct["renamemovies"] = renamemovies


if args.renamephotos == None:
	renamephotos = Photodelivercfg.renamephotos
else:
	renamephotos = [False,True][args.renamephotos]
parametersdyct["renamephotos"] = renamephotos


if args.eventminpictures == None:
	eventminpictures = Photodelivercfg.eventminpictures
else:
	eventminpictures = args.eventminpictures
parametersdyct["eventminpictures"] = eventminpictures


if args.gap == None:
	gap = Photodelivercfg.gap
else:
	gap = args.gap
parametersdyct["gap"] = gap


if args.copymode == None:
	copymode = Photodelivercfg.copymode
else:
	copymode = args.copymode
parametersdyct["copymode"] = copymode


if args.considerdestinationitems == None:
	considerdestinationitems = Photodelivercfg.considerdestinationitems
else:
	considerdestinationitems = [False,True][args.considerdestinationitems]
parametersdyct["considerdestinationitems"] = considerdestinationitems


if args.moveexistentfiles == None:
	moveexistentfiles = Photodelivercfg.moveexistentfiles
else:
	moveexistentfiles = [False,True][args.moveexistentfiles]
parametersdyct["moveexistentfiles"] = moveexistentfiles


if args.ignoreTrash == None:
	ignoreTrash = Photodelivercfg.ignoreTrash
else:
	ignoreTrash = [False,True][args.ignoreTrash]
parametersdyct["ignoreTrash"] = ignoreTrash


if args.preservealbums == None:
	preservealbums = Photodelivercfg.preservealbums 
else:
	preservealbums = [False,True][args.preservealbums]
parametersdyct["preservealbums"] = preservealbums


if args.forceassignfromfilename == None:
	forceassignfromfilename = Photodelivercfg.forceassignfromfilename
else:
	forceassignfromfilename = [False,True][args.forceassignfromfilename]
parametersdyct["forceassignfromfilename"] = forceassignfromfilename


if args.cleaning == None:
	cleaning = Photodelivercfg.cleaning
else:
	cleaning = [False,True][args.cleaning]
parametersdyct["cleaning"] = cleaning


if args.storefilemetadata == None:
	storefilemetadata = Photodelivercfg.storefilemetadata
else:
	storefilemetadata = [False,True][args.storefilemetadata]
parametersdyct["storefilemetadata"] = storefilemetadata


if args.convert == None:
	convert = Photodelivercfg.convert
else:
	convert = [False,True][args.convert]
parametersdyct["convert"] = convert

# ===============================
# The logging module.
# ===============================
loginlevel = 'DEBUG'
logpath = './'
logging_file = os.path.join(logpath, 'Photodeliver.log')


# Getting current date and time
now = datetime.datetime.now()
today = "/".join([str(now.day), str(now.month), str(now.year)])
tohour = ":".join([str(now.hour), str(now.minute)])

print ("Loginlevel:", loginlevel)
logging.basicConfig(
	level = loginlevel,
	format = '%(asctime)s : %(levelname)s : %(message)s',
	filename = logging_file,
	filemode = 'w'  # a = add
)
print ("logging to:", logging_file)


# Starting log file
logging.info("======================================================")
logging.info("================ Starting a new run===================")
logging.info("======================================================")
logging.info('From:' + originlocation)
logging.info('  To:' + destlocation)


# Check inconsistences
errmsgs = []

#-ol
if originlocation != '':
	if itemcheck(originlocation) != 'folder':
		errmsgs.append ('\nSource folder does not exist:\n-ol\t'+originlocation)
		logging.critical('Source folder does not exist: ' + originlocation)
	originlocation = addslash (originlocation)

else:
	if moveexistentfiles == True :
		print ('Origin location have been not entered, this will reagroup destlocation items.')
		logging.info ('No origin location entered: Reagrouping existent pictures')
	else:
		errmsgs.append ('No origin location was introduced, and you do not want to reagroup existent items.')
		logging.critical ('No origin location was introduced, and no interaction was selected.')
		
#-dl
if itemcheck(destlocation) != 'folder':
	errmsgs.append ('\nDestination folder does not exist:\n-dl\t' + str(destlocation))
	logging.critical('Source folder does not exist')
destlocation = addslash (destlocation)
 
#-rm
if type (renamemovies) is not bool :
	errmsgs.append ('\nRenamemovies parameter can only be True or False:\n-rm\t' + str(renamemovies))
	logging.critical('renamemovies parameter is not True nor False')

#-rp
if type (renamephotos) is not bool :
	errmsgs.append ('\nRenamephotos parameter can only be True or False:\n-rp\t' + str(renamephotos))
	logging.critical('renamephotos parameter is not True nor False')

#-minp
if type(eventminpictures) is not int :
	errmsgs.append ('\neventminpictures parameter can only be an integer:\n-minp\t' + str(eventminpictures))
	logging.critical('eventminpictures parameter is not an integer')

#-gap
if type(gap) is not int :
	errmsgs.append ('\ngap parameter can only be an integer:\n-gap\t' + str(gap))
	logging.critical('gap parameter is not an integer')

#-cpmode
if copymode not in ['c','m'] :
	errmsgs.append ('\ncopymode parameter can only be c or m:\n-copymode\t' + str(copymode))
	logging.critical('copymode parameter is not c nor m')

#-cdi
if type (considerdestinationitems) is not bool :
	errmsgs.append ('\nconsiderdestinationitems parameter can only be True or False:\n-cdi\t' + str(considerdestinationitems))
	logging.critical('considerdestinationitems parameter is not True nor False')

#-mef
if type (moveexistentfiles) is not bool :
	errmsgs.append ('\nmoveexistentfiles parameter can only be True or False:\n-mef\t' + str(moveexistentfiles))
	logging.critical('moveexistentfiles parameter is not True nor False')

#-it
if type (ignoreTrash) is not bool :
	errmsgs.append ('\nignoreTrash parameter can only be True or False:\n-it\t' + str(ignoreTrash))
	logging.critical('ignoreTrash parameter is not True nor False')

#-pa
if type (preservealbums) is not bool :
	errmsgs.append ('\npreservealbums parameter can only be True or False:\n-pa\t' + str(preservealbums))
	logging.critical('preservealbums parameter is not True nor False')

#-faff
if type (forceassignfromfilename) is not bool :
	errmsgs.append ('\nforceassignfromfilename parameter can only be True or False:\n-faff\t' + str(forceassignfromfilename))
	logging.critical('forceassignfromfilename parameter is not True nor False')

#-clean
if type (cleaning) is not bool :
	errmsgs.append ('\ncleaning parameter can only be True or False:\n-clean\t' + str(cleaning))
	logging.critical('cleaning parameter is not True nor False')

#-sfm
if type (storefilemetadata) is not bool :
	errmsgs.append ('\nstorefilemetadata parameter can only be True or False:\n-fb\t' + str(storefilemetadata))
	logging.critical('storefilemetadata parameter is not True nor False')

#-conv
if type (convert) is not bool :
	errmsgs.append ('\nconvert parameter can only be True or False:\n-conv\t' + str(convert))
	logging.critical('convert parameter is not True nor False')

# exitting if errors econuntered
if len (errmsgs) != 0 :
	for a in errmsgs:
		print (a)
	print ('\nplease revise your config file or your command line arguments.','Use --help or -h for some help.','\n ....exitting',sep='\n')
	exit()


# adding to log file Running parameters
for a in parametersdyct:
	text = a + " = "+ str(parametersdyct[a]) + " \t (from args:"+ str(eval ("args." + a)) + ") \t (At config file: "+ str(eval ("Photodelivercfg." + a))+ ")"
	logging.info (text)
	if args.showconfig :
		print (text+ "\n")

if args.dummy:
	logging.info("-------------- Running in Dummy mode ------------")

# exitting if show config was enabled.
if args.showconfig :
	print ("exitting...")
	exit()

def readmetadate (metadata, exif_key):
	metadate = metadata.get(exif_key)
	if not (metadate == None or metadate.strip() == ''):
		logging.debug (exif_key + ' found:' + metadate)
	else:
		logging.debug ('No '+ exif_key + 'found.')
	return metadate

def lsdirectorytree( directory = os.getenv( 'HOME')):
	""" Returns a list of a directory and its child directories

	usage:
	lsdirectorytree ("start directory")
	By default, user's home directory"""
	#init list to start
	dirlist = [directory]
	#setting the first scan
	moredirectories = dirlist
	while len(moredirectories) != 0:
		newdirectories = moredirectories
		#reset flag to 0; we assume from start, that there aren't child directories
		moredirectories = []
		# print ('\n\n\n','nueva iteración', moredirectories)
		for a in newdirectories:
			# checking for items (child directories)
			# print ('Checking directory', a)
			añadir = addchilddirectory(a)
			#adding found items to moredirectories
			for b in añadir:
				moredirectories.append(b)
		#adding found items to dirlist
		for a in moredirectories:
			dirlist.append(a)
	return dirlist

def addchilddirectory(directorio):
	""" Returns a list of child directories

	Usage: addchilddirectory(directory with absolute path)"""
	paraañadir = []
	ficheros = os.listdir(directorio)
	#print ('ficheros encontrados en: ',directorio, ':\n' , ficheros, '\n')
	for a in ficheros:
		item = os.path.join(directorio, a)
		#check, and if directory, it's added to paths-list
		if os.path.isdir(item):
			# print('Directory found: '+ item)
			# print('Añadiendo elemento para escanear')
			paraañadir.append(item)
	# print ('este listado hay que añadirlo para el escaneo: ', paraañadir)
	return paraañadir

def Nextfilenumber (dest):
	''' Returns the next filename counter as filename(nnn).ext
	input: /path/to/filename.ext
	output: /path/to/filename(n).ext
		'''
	filename = os.path.basename (dest)
	extension = os.path.splitext (dest)[1]
	# extract secuence
	expr = '\(\d{1,}\)'+extension
	mo = re.search (expr, filename)
	try:
		grupo = mo.group()
	except:
		#  print ("No final counter expression was found in %s. Counter is set to 0" % dest)
		counter = 0
		cut = len (extension)
	else:
		#  print ("Filename has a final counter expression.  (n).extension ")
		cut = len (mo.group())
		countergroup = (re.search ('\d{1,}', grupo))
		counter = int (countergroup.group()) + 1
	if cut == 0 :
		newfilename = os.path.join( os.path.dirname(dest), filename + "(" + str(counter) + ")" + extension)
	else:
		newfilename = os.path.join( os.path.dirname(dest), filename [0:-cut] + "(" + str(counter) + ")" + extension)
	return newfilename

def mediaadd(item):
	#1) Retrieve basic info from the file
	logging.debug ('## item: '+ item)
	abspath = item
	filename, fileext = os.path.splitext(os.path.basename (abspath))
	Statdate = datetime.datetime.utcfromtimestamp(os.path.getmtime (abspath))
	filebytes = os.path.getsize(abspath)  # logging.debug ('fileTepoch (from Stat): '.ljust( justif ) + str(fileTepoch))
	fnDateTimeOriginal = None  # From start we assume a no date found on the file path

	#2) Fetch date identificators form imagepath, serie and serial number if any. 
	mintepoch = 1900  # In order to discard low year values, this is the lowest year. 

	# Try to find some date structure in folder paths. (abspath)
	''' Fetch dates from folder structure, this prevents losing information if exif metadata 
	doesn't exist. Metada can be lost if you modify files with software. It is also usefull 
	if you move video files (wich doesn't have exif metadata) among cloud services.
	Pej. you can store a folder structure in your PC client dropbox, and you'll lose your "stat" date,
	 but you can always recover it from file name/path.
	Structures:
		Years:
			one of the path-folder starts as a year number with four numbers
				[12]\d{3}    YYYY
		Months:
			one of the path folders is a month numbers
		Combos:
			one of the path folders starts with YYYY-MM

		Full date:
			there is a full-date structure on the path.
			2015-01-04 | 2015_01_04 | 2015:01:04 | 2015 01 04

		The day, hour-minutes and seconds asigned are 01, 12:00:00 + image serial number (in seconds) for each image to preserve an order.
		'''
	## Cutting main tree from fullpaths.
	if abspath.startswith (originlocation):
		branch = abspath[ len ( originlocation ):]
	else:
		branch = abspath[ len ( destlocation ):]
	pathlevels = os.path.dirname (branch).split ('/')
	# Removig not wanted slashes
	if '' in pathlevels:
		pathlevels.remove('')
	logging.debug ('Found directories levels: '+str(pathlevels))
	# Starting variables. From start, we assume that there is no date at all.
	fnyear = None
	fnmonth = None
	fnday = '01'
	fnhour = '12'
	fnmin = '00'
	fnsec = '00'
	# C1 - /*Year*/ /month/ /day/ in pathlevels (year must be detected from an upper level first)
	for word in pathlevels:
		wordslash = "/"+word+"/"
			#possible year is a level path:
		expr = "/(?P<year>[12]\d{3})/"
		mo = re.search(expr, wordslash)
		try:
			mo.group()
		except:
			pass
		else:
			if int(mo.group('year')) in range (mintepoch, 2038):
				fnyear = mo.group ('year')
				logging.debug( 'found possible year in '+ wordslash +':'+fnyear)
				continue

				#possible month is a level path:
		if len (word) == 2 and word.isnumeric ():
			if int(word) in range(1,13):
				fnmonth = word
				logging.debug( 'found possible month in'+ word +':'+fnmonth)
				continue

				#possible day is a level path:
		if len (word) == 2 and word.isnumeric ():
			if int(word) in range(1,32):
				fnday = word
				logging.info( 'found possible day in'+ word +':'+fnday)
				continue

		# C2 (Year-month)
		expr = ".*(?P<year>[12]\d{3})[-_ /]?(?P<month>[01]\d).*"
		mo = re.search(expr, wordslash)
		try:
			mo.group()
		except:
			pass
		else:
			if int (mo.group('month')) in range (1,13) and int(mo.group('year')) in range (mintepoch, 2038):
				fnyear = mo.group ('year')
				fnmonth = mo.group ('month')
				logging.debug( 'found possible year-month in'+ wordslash +':'+fnyear+" "+fnmonth)

		# C3: (Year-month-day)
		expr = "(?P<year>[12]\d{3})[-_ /]?(?P<month>[01]\d)[-_ /]?(?P<day>[0-3]\d)"
		mo = re.search(expr, wordslash)
		try:
			mo.group()
		except:
			pass
		else:
			if int(mo.group('year')) in range (mintepoch, 2038) and int (mo.group('month')) in range (1,13) and int (mo.group ('day')) in range (1,32):
				fnyear = mo.group ('year')
				fnmonth = mo.group ('month')
				fnday = mo.group ('day')
				logging.debug( 'found possible year-month-day in' + wordslash + ':' + fnyear + " " + fnmonth + " " + fnday)


	# C4: YYYYMMDD-HHMMSS  in filename
	Imdatestart = False  # Flag to inform a starting full-date-identifier at the start of the file.
	expr = '(?P<year>[12]\d{3})[-_ .:]?(?P<month>[01]\d)[-_ .:]?(?P<day>[0-3]\d)[-_ .:]?(?P<hour>[012]\d)[-_ .:]?(?P<min>[0-5]\d)[-_ .:]?(?P<sec>[0-5]\d)'
	mo = re.search (expr, filename)
	try:
		mo.group()
	except:
		logging.debug ("expression %s Not found in %s" %(expr, filename))
		pass
	else:			
		if int(mo.group('year')) in range (mintepoch, 2038):
			fnyear  = mo.group ('year')
			fnmonth = mo.group ('month')
			fnday   = mo.group ('day')
			fnhour  = mo.group ('hour')
			fnmin   = mo.group ('min')
			fnsec   = mo.group ('sec')
			logging.debug ( 'found full date identifier in ' + filename)
			if mo.start() == 0 :
				logging.debug ('filename starts with a full date identifier: '+ filename )
				Imdatestart = True  #  True means that filename starts with full-date serial in its name (item will not add any date in his filename again)


	# setting creation date retrieved from filepath
	if fnyear != None and fnmonth != None:
		textdate = '%s:%s:%s %s:%s:%s'%(fnyear, fnmonth, fnday, fnhour, fnmin, fnsec)
		logging.debug ('This date have been retrieved from the file-path-name: ' + textdate )
		fnDateTimeOriginal = datetime.datetime.strptime (textdate, '%Y:%m:%d %H:%M:%S')



	# Serial number
	seriallist = ['WA[-_ ]?[0-9]{4}',
					'IMG[-_ ]?[0-9]{4}',
					'PICT[-_ ]?[0-9]{4}',
					'MVI[-_ ]?[0-9]{4}'
					]
	serialdict = { seriallist[0]: '(?P<se>WA)[-_ ]?(?P<sn>[0-9]{4})',
					seriallist[1] : '(?P<se>IMG)[-_ ]?(?P<sn>[0-9]{4})',
					seriallist[2] : '(?P<se>PICT)[-_ ]?(?P<sn>[0-9]{4})',
					seriallist[3] : '(?P<se>MVI)[-_ ]?(?P<sn>[0-9]{4})'}
	sf = False
	for expr in seriallist :
		mo = re.search (expr, filename)
		try:
			mo.group()
		except:
			logging.debug ("expression %s Not found in %s" %(expr, filename))
			continue
		else:
			mo = re.search ( serialdict[expr], filename)
			logging.debug ("expression %s found in %s" %(expr, filename))
			sf = True
			break
	# setting serie and serial number
	if sf == True:
		imserie  = mo.group ('se')
		imserial = mo.group ('sn')
		logging.debug ( 'Item serie and serial number (' + filename + '): '+ imserie + ' ' +  imserial)
	else:
		imserie  = None
		imserial = None	
	

	# Fetch image metadata (if any) 
	textdate = None
	MetaDateTimeOriginal = None
	if fileext.lower() in ['.jpg', '.jpeg', '.raw', '.png']:
		metadata = GExiv2.Metadata(abspath)
		
		ImageModel = readmetadate( metadata ,'Exif.Image.Model')
		ImageMake = readmetadate( metadata ,'Exif.Image.Make')
		textdate = readmetadate( metadata ,'Exif.Photo.DateTimeOriginal')
		if textdate == None:
			textdate = readmetadate( metadata ,'Exif.Photo.DateTimeDigitized')
			if textdate == None:
				textdate = readmetadate( metadata ,'Exif.Image.DateTime')
		
		if textdate != None: 
			MetaDateTimeOriginal = datetime.datetime.strptime (textdate, '%Y:%m:%d %H:%M:%S')


	# Decide media date of creation
	''' Decide and assign the right media cration time due to:
	its metadata
	<path/file name>
	or from stat
	'''
	TimeOriginal = None  # From start we assign None if no matches are found.
	decideflag = None  # Flag storing the decision.

	# Set Creation Date from Metadata if it is found,
	if MetaDateTimeOriginal != None and forceassignfromfilename == False:
		TimeOriginal = MetaDateTimeOriginal
		decideflag = 'Metadata'
		logging.debug ('Image Creation date has been set from image metadata: ' + str(TimeOriginal))
	else:
		# Set Creation Date extracted from filename/path
		if fnDateTimeOriginal != None :
			TimeOriginal = fnDateTimeOriginal
			decideflag = 'Filepath'
			logging.debug ('Image Creation date has been set from File path / name: '+ str(TimeOriginal))

		elif abspath.find('DCIM') != -1:
			# Set Creation Date from stat file.
			'''
			(You only should use this if you have those pictures in the original media storage
			without modifications and you want to read it directly from the media. or
			The files have been copied among filesystem that preserves the file creation date, usually ext3 ext4, NTFs, or MacOSx filesystems.
			See file properties first and ensure that you can trust its date of creation. Anyway, the file only will be processed
			if in its path is the word DCIM.)
				'''
			TimeOriginal = Statdate
			decideflag = 'Stat'
			logging.debug ( "Image Creation date has been set from File stat" )

	if TimeOriginal == None :
		logging.debug ( "Can't guess Image date of Creation" )


	con.execute ('INSERT INTO files (Fullfilepath, Filename, Fileext, Filebytes, Imdatestart,Pathdate, Exifdate, Statdate , Timeoriginal , Decideflag, Imgserie, Imgserial) \
		VALUES (?,?,?,?,?,?,?,?,?,?,?,?)', [ item, filename, fileext, filebytes, Imdatestart,fnDateTimeOriginal, MetaDateTimeOriginal, Statdate, TimeOriginal, decideflag, imserie, imserial ])

def mediascan(location):
	
	# 1.1) get items dir-tree
	listree = lsdirectorytree (location)
	nfilesscanned = 0

	# 1.2) get a list of media items and casting into a class

	for d in listree:
		for ext in wantedmedia:
			itemlist = list()
			itemlist += glob(os.path.join(d,'*.'+ ext.lower()))
			itemlist += glob(os.path.join(d,'*.'+ ext.upper()))
			if len (itemlist) > 0:
				for a in itemlist:
					if ignoreTrash == True : 
						if a.find ('.Trash') != -1 :
							logging.debug ('Item %s was not included (Trash folder)' %(a) )
							continue
						if a.find ('.thumbnails') != -1 :
							logging.debug ('Item %s was not included (Thumbnails folder)' %(a) )
							continue
					mediaadd (a)  # Add item info to DB
					nfilesscanned += 1
	msg = str(nfilesscanned) + ' files where scanned at ' + location
	print (msg); logging.info (msg)
	return nfilesscanned

# ===========================================
# ========= Main module =====================
# ===========================================


# 0) Start tmp Database

if itemcheck (dbpath) == "file":
	os.remove (dbpath)
	logging.info("Older tmp database found, it has been deleted.")

con = sqlite3.connect (dbpath) # it creates one if it doesn't exists
cursor = con.cursor() # object to manage queries

# 0.1) Setup DB
cursor.execute ('CREATE TABLE files (\
	Fullfilepath char NOT NULL ,\
	Filename char NOT NULL ,\
	Fileext char  ,\
	Targetfilepath char  ,\
	Filebytes int NOT NULL ,\
	Imdatestart Boolean, \
	Exifdate date  ,\
	Pathdate date  ,\
	Statdate date NOT NULL,\
	Timeoriginal date, \
	Decideflag char, \
	Convertfileflag Boolean, \
	Imgserie char, \
	Imgserial char, \
	EventID int, \
	Eventdate date \
	)')
con.commit()

# 1) Get items
# 1.1) Retrieving items to process

Totalfiles = 0
if not (originlocation == '' or originlocation == destlocation):
	nfilesscanned = mediascan (originlocation)
	Totalfiles += nfilesscanned
	con.commit()

nfilesscanned = mediascan (destlocation)
Totalfiles += nfilesscanned
con.commit()

msg = '-'*20+'\n'+ str(Totalfiles) + ' Total files scanned'
print (msg); logging.info (msg)
if Totalfiles == 0 :
	print ('Nothing to import / reagroup.')
	logging.warning ('Thereis nothing to import or reagroup, please revise your configuration, exitting....')
	exit()


# 1.2) Show general info
cursor.execute ("SELECT count (Fullfilepath) FROM files WHERE Decideflag = 'Metadata'")
nfiles = ((cursor.fetchone())[0])
msg = str(nfiles) + ' files already had metadata and will preserve it.'
print (msg); logging.info (msg)

cursor.execute ("SELECT count (Fullfilepath) FROM files WHERE Decideflag = 'Filepath' and Exifdate is NULL")
nfiles = ((cursor.fetchone())[0])
msg = str(nfiles) + ' files have not date metadata and a date have been retrieved from the filename or the path.'
print (msg); logging.info (msg)

cursor.execute ("SELECT count (Fullfilepath) FROM files WHERE Decideflag = 'Filepath' and Exifdate is not NULL")
nfiles = ((cursor.fetchone())[0])
msg = str(nfiles) + ' files have a date metadata but a date have been retrieved from the filename or the path and it will rewritted (-faff option has been activated).'
print (msg); logging.info (msg)

cursor.execute ("SELECT count (Fullfilepath) FROM files WHERE Decideflag = 'Stat'")
nfiles = ((cursor.fetchone())[0])
msg = str(nfiles) + ' files does not have date metadata, is also was not possible to find a date on their paths or filenames, and their date of creation will be assigned from the file creation date (Stat).'
print (msg); logging.info (msg)

cursor.execute ("SELECT count (Fullfilepath) FROM files WHERE Decideflag is NULL ")
nfiles = ((cursor.fetchone())[0])
msg = str(nfiles) + ' files does not have date metadata, is also was not possible to find a date on their paths or filenames. Place "DCIM" as part of the folder or file name at any level if you want to assign the filesystem date as date of creation.'
print (msg); logging.info (msg)




# 2) Processing items 
# 2.1) Grouping in events, máx distance is gap seconds

if gap > 0:
	if considerdestinationitems == True:
		#considering all items
		cursor.execute ('SELECT Fullfilepath, Timeoriginal FROM files where Timeoriginal is not NULL ORDER BY Timeoriginal')
	else:
		#considering only items at origin folder
		cursor.execute ("SELECT Fullfilepath, Timeoriginal FROM files where Timeoriginal is not NULL and Fullfilepath LIKE '%s'  ORDER BY Timeoriginal" %(originlocation+"%"))

	regcounter = 0
	eventID = 0
	timegap = datetime.timedelta(days=0, seconds=gap, microseconds=0, milliseconds=0, minutes=0, hours=0)
	msg = "Group option is activated (-gap option). This will group Pictures closer in time than " + str(timegap) + " in an event day."
	print (msg); logging.info (msg)

	for i in cursor:
		regcounter += 1
		Fullfilepath1, Timestr = i
		TimeOriginal1 = datetime.datetime.strptime (Timestr, '%Y-%m-%d %H:%M:%S')
		if regcounter == 1 :
			TimeOriginal0 = TimeOriginal1
			Fullfilepath0 = Fullfilepath1
			con.execute ("UPDATE files set EventID=0 where Fullfilepath = '%s'" %(Fullfilepath1))
			continue
		diff = TimeOriginal1-TimeOriginal0
		if diff <= timegap :
			logging.debug  ('this picture is part of an event with the preceding one')
		else:
			logging.debug ('this picture is not part of an event with the preceding one')
			eventID += 1
		con.execute ("UPDATE files set EventID=%s where Fullfilepath = '%s'" %(eventID, Fullfilepath1))

		TimeOriginal0 = TimeOriginal1
		Fullfilepath0 = Fullfilepath1
		# print (regcounter, eventID, i[1])
	con.commit()

	#2.2) Inform de date of the event. (The minimun date)
	for i in range (0,eventID+1):
		# count number of files in that event: 
		cursor.execute ('SELECT count (Fullfilepath), MIN (Timeoriginal) FROM files where EventID = %s' %(i))
		nfiles, eventdate = cursor.fetchone()
		#print (i, nfiles, eventdate)
		# Set event date if it has the minimun number required.
		if nfiles >= eventminpictures:
			print ('')
			con.execute ("UPDATE files set Eventdate='%s' where EventID = %s" %(eventdate ,i))
	con.commit()


# 3) Set Target files for items
cursor.execute ('SELECT Fullfilepath, Timeoriginal, Eventdate, Filename, Fileext, Filebytes,Imdatestart FROM files ORDER BY Timeoriginal')
for i in cursor:
	a, Timeoriginal, Eventdate, Filename, fileext, filebytes,Imdatestart = i
	eventname = ''
	eventnameflag = False

	# 3.1) Skipping processing a new path to files into destination folder if moveexistentfiles is False
	if a.startswith(destlocation) and moveexistentfiles == False:
		logging.debug ('Item %s was not included (moveexistentfiles option is False)' %(a) )
		continue

	# 3.2) item's fullpath and filename
	if preservealbums == True and a.find ('_/') != -1 :
		if a.startswith (destlocation) :
			logging.debug ('Item %s was not included (Preserving album folder at destination location).' %(a) )
		else:
			logging.debug ('Moving item %s to destination preserving its path (is part of an album).' %(a) )
			dest = os.path.join(destlocation, a.replace(originlocation,''))
		continue

	else:
		if Timeoriginal == None:
			logging.debug ('Moving item %s to nodate folder (it has no date).' %(a) )			
			if a.startswith(os.path.join(destlocation,"nodate")):
				dest = a
			else:
				if a.startswith(destlocation):
					dest = os.path.join(destlocation, "nodate", a.replace(destlocation,''))
				else:
					dest = os.path.join(destlocation, "nodate", a.replace(originlocation,''))

		else:
			itemcreation = datetime.datetime.strptime (Timeoriginal, '%Y-%m-%d %H:%M:%S')  # Item has a valid date, casting it to a datetime object.
			# Check origin dir Structure for an already event name
			'''
			#  /YYYY-MM Xeventname/
			expr = "/[12]\d{3}[-_ ]?[01]\d ?(?P<XeventnameX>.*)/"
			mo = re.search(expr, a)
			try:
				mo.group()
			except:
				pass
			else:
				eventnameflag = True
				eventname = mo.group('XeventnameX')
			'''
			#  /YYYY-MM-DD Xeventname/
			expr = "/[12]\d{3}[-_ ]?[01]\d[-_ ]?[0-3]\d ?(?P<XeventnameX>.*)/"
			mo = re.search(expr, a)
			try:
				mo.group()
			except:
				pass
			else:
				eventnameflag = True
				eventname = mo.group('XeventnameX')

			# retrieve the name & set Even-Flag to True
			if eventnameflag == True:
				logging.debug( 'found an origin event name in: %s (%s)' %(a, eventname))



			# Getting a possible event day
			# deliver
			if eventnameflag == True or Eventdate is not None:
				#destination includes a day - event
				if Eventdate == None:
					Eventdate = itemcreation
				else:
					Eventdate = datetime.datetime.strptime (Eventdate, '%Y-%m-%d %H:%M:%S')
				dest = os.path.join(destlocation, Eventdate.strftime('%Y'), Eventdate.strftime('%Y-%m-%d'), os.path.basename(a))
				eventnameflag = True
			else:
				#destination only includes a month (go to a various month-box)
				dest = os.path.join(destlocation, itemcreation.strftime('%Y'), itemcreation.strftime('%Y-%m'), os.path.basename(a))
			# set date information in filename.
			if ((renamemovies == True and fileext.lower()[1:] in moviesmedia) or ( renamephotos == True and fileext.lower()[1:] in photomedia)) and Imdatestart != True :
				dest = os.path.join(os.path.dirname(dest), itemcreation.strftime('%Y%m%d_%H%M%S') + "-" + os.path.basename(dest) )
	
	# 3.3) Adding event name in the path
	if eventnameflag == True:
		destcheck = os.path.dirname(dest)  # Check destination dir structure ../../aaaa/aaaa-mm-dd*
		levents = glob(destcheck + '*')
		if len (levents) != 0 :
			# (Get event path as existing path for destination)
			dest = os.path.join(levents.pop(), os.path.basename(dest))
		else:
			if eventname != '':
				eventname = " "+ eventname
			dest = os.path.join(os.path.dirname(dest) + eventname, os.path.basename(dest) )
	# 3.4) Set convert flag
	convertfileflag = False
	if convert == True and fileext.lower() in [".png",".bmp",]:
		dest = os.path.splitext(dest)[0]+".jpg"
		convertfileflag = True
	
	# 3.5) Checkig if it is a duplicated file.
	while True:
		if itemcheck (dest) == '':
			break
		else:
			if filebytes != os.path.getsize(dest):
				dest = Nextfilenumber (dest)
				continue
			else:
				if a.startswith (os.path.join(originlocation,dupfoldername)) or dest.startswith (os.path.join(originlocation,dupfoldername)) or a.startswith (destlocation) :
					logging.warning('destination item already exists')
					dest = a
					break
				else:
					dest = os.path.join (originlocation,dupfoldername, a.replace(originlocation,''))
					continue

	con.execute ("UPDATE files set Targetfilepath = '%s', Convertfileflag = '%s' where Fullfilepath = '%s'" %(dest , convertfileflag, a))
con.commit()


# 4) Perform file operations
foldercollection = set ()
cursor.execute ('SELECT Fullfilepath, Targetfilepath, Fileext, Timeoriginal, Decideflag, Convertfileflag FROM files WHERE Targetfilepath <> Fullfilepath and Targetfilepath IS NOT NULL')
for i in cursor:
	a, dest, fileext, TimeOriginal, decideflag, convertfileflag = i
	logging.info ('')
	logging.info ('Processing:')
	logging.info (a)
	if itemcheck (os.path.dirname(dest)) == '':
			if args.dummy != True:
				os.makedirs (os.path.dirname(dest))
	# Convert to JPG Option
	if convertfileflag == True:
		logging.info ("\t Converting to .jpg")
		picture = Image.open (a)
		if args.dummy != True:
			picture.save (dest)
		picture.close()  # commented for ubuntu 14.10 comtabilitiy
	else:
		if args.dummy != True:
			shutil.copy (a, dest)
		logging.info ('\t file successfully copied into destination.')
	if copymode == 'm':
		if args.dummy != True:
			os.remove (a)
		logging.info ('\t origin file successfully deleted.')
		if cleaning == True:
			foldercollection.add (os.path.dirname(a))
	
	# Write metadata into the file-archive
	if storefilemetadata == True and fileext.lower()[1:] not in moviesmedia and decideflag in ['Filepath','Stat']:
		if args.dummy != True:
			metadata = GExiv2.Metadata(dest)
			itemcreation = datetime.datetime.strptime (Timeoriginal, '%Y-%m-%d %H:%M:%S')  # Item has a valid date, casting it to a datetime object.
			metadata.set_date_time(itemcreation)
			metadata.save_file()
		logging.info ('\t' + 'writed metadata to image file.')
	logging.info ('\t' + dest)

#4) Cleaning empty directories
if cleaning == True:
	logging.info ('='*10)
	logging.info ('Checking empty folders to delete them')
	foldercollectionnext = set()
	while len(foldercollection) > 0:
		for i in foldercollection:
			logging.info ('checking: %s' %i)
			if itemcheck(i) != 'folder':
				logging.warning ('\tDoes not exists or is not a folder. Skipping')
				continue			
			if len (os.listdir(i)) == 0:
				if args.dummy != True: 
					shutil.rmtree (i)
				logging.info ('\tfolder has been removed. (was empty)')
				foldercollectionnext.add (os.path.dirname(i))
				logging.debug ('\tadded next level to re-scan')
		foldercollection = foldercollectionnext
		foldercollectionnext = set()

#5) Done
print ('Done!')
''' print a little resumen '''