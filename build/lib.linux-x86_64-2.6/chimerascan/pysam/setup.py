#!/usr/bin/python
'''

pysam
*****

'''

import os, sys, glob, shutil, hashlib

name = "pysam"

# collect pysam version
sys.path.insert( 0, "pysam")
import version

version = version.__version__

samtools_exclude = ( "bamtk.c", "razip.c", "bgzip.c", "errmod.c", "bam_reheader.c", "bam2bcf.c" )
samtools_dest = os.path.abspath( "samtools" )
tabix_exclude = ( "main.c", )
tabix_dest = os.path.abspath( "tabix" )

# copy samtools source
if len(sys.argv) >= 2 and sys.argv[1] == "import":
   if len(sys.argv) < 3: raise ValueError("missing PATH to samtools source directory")
   if len(sys.argv) < 4: raise ValueError("missing PATH to tabix source directory")

   for destdir, srcdir, exclude in zip( 
      (samtools_dest, tabix_dest), 
      sys.argv[2:4],
      (samtools_exclude, tabix_exclude)):

      srcdir = os.path.abspath( srcdir )
      if not os.path.exists( srcdir ): raise IOError( "samtools src dir `%s` does not exist." % srcdir )

      cfiles = glob.glob( os.path.join( srcdir, "*.c" ) )
      hfiles = glob.glob( os.path.join( srcdir, "*.h" ) )
      ncopied = 0
      for new_file in cfiles + hfiles:
         f = os.path.basename(new_file)
         if f in exclude: continue
         old_file = os.path.join( destdir, f )
         if os.path.exists( old_file ):
            md5_old = hashlib.md5("".join(open(old_file,"r").readlines())).digest()
            md5_new = hashlib.md5("".join(open(new_file,"r").readlines())).digest()
            if md5_old == md5_new: continue
            raise ValueError( "incompatible files for %s and %s" % (old_file, new_file ))

         shutil.copy( new_file, destdir )
         ncopied += 1
      print "installed latest source code from %s: %i files copied" % (srcdir, ncopied)
   sys.exit(0)

from distutils.core import setup, Extension
from Cython.Distutils import build_ext

classifiers = """
Development Status :: 2 - Alpha
Operating System :: MacOS :: MacOS X
Operating System :: Microsoft :: Windows :: Windows NT/2000
Operating System :: OS Independent
Operating System :: POSIX
Operating System :: POSIX :: Linux
Operating System :: Unix
Programming Language :: Python
Topic :: Scientific/Engineering
Topic :: Scientific/Engineering :: Bioinformatics
"""

samtools = Extension(
    "csamtools",                   # name of extension
    [ "pysam/csamtools.pyx" ]  +\
       [ "pysam/%s" % x for x in (
             "pysam_util.c", )] +\
       glob.glob( os.path.join( "samtools", "*.c" ) ),
    library_dirs=[],
    include_dirs=[ "samtools", "pysam" ],
    libraries=[ "z", ],
    language="c",
    define_macros = [('FILE_OFFSET_BITS','64'),
                     ('_USE_KNETFILE','')], 
    )

tabix = Extension(
    "ctabix",                   # name of extension
    [ "pysam/ctabix.pyx" ]  +\
       [ "pysam/%s" % x for x in ()] +\
       glob.glob( os.path.join( "tabix", "*.c" ) ),
    library_dirs=[],
    include_dirs=[ "tabix", "pysam" ],
    libraries=[ "z", ],
    language="c",
    )

metadata = {
    'name': name,
    'version': version,
    'description': "pysam", 
    'long_description': __doc__,
    'author': "Andreas Heger",
    'author_email': "andreas.heger@gmail.com",
    'license': "MIT",
    'platforms': "ALL",
    'url': "http://code.google.com/p/pysam/",
    'py_modules': [
      "pysam/__init__", 
      "pysam/Pileup", 
      "pysam/namedtuple",
      "pysam/version" ],
    'ext_modules': [samtools, tabix],
    'cmdclass' : {'build_ext': build_ext},
    }

if __name__=='__main__':
   dist = setup(**metadata)
