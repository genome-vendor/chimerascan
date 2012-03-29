'''Tools for working with files in the samtools pileup -c format.'''
import collections

PileupSubstitution = collections.namedtuple( "PileupSubstitution",
                                    " ".join( (\
            "chromosome", 
            "position", 
            "reference_base", 
            "consensus_base",
            "consensus_quality",
            "snp_quality",
            "rms_mapping_quality",
            "coverage",
            "read_bases",
            "base_qualities" ) ) )

PileupIndel = collections.namedtuple( "PileupIndel",
                                      " ".join( (\
            "chromosome", 
            "position", 
            "reference_base", 
            "genotype",
            "consensus_quality",
            "snp_quality",
            "rms_mapping_quality",
            "coverage",
            "first_allelle",
            "second_allele",
            "reads_first",
            "reads_second",
            "reads_diff" ) ) )

def iterate( infile ):
    '''iterate over ``samtools pileup -c`` formatted file.

    *infile* can be any iterator over a lines.

    The function yields named tuples of the type :class:`pysam.Pileup.PileupSubstitution`
    or :class:`pysam.Pileup.PileupIndel`.

    .. note:: 
       The parser converts to 0-based coordinates
    '''
    
    conv_subst = (str,lambda x: int(x)-1,str,str,int,int,int,int,str,str)
    conv_indel = (str,lambda x: int(x)-1,str,str,int,int,int,int,str,str,int,int,int)

    for line in infile:
        d = line[:-1].split()
        if d[2] == "*":
            try:
                yield PileupIndel( *[x(y) for x,y in zip(conv_indel,d) ] )
            except TypeError:
                raise SamtoolsError( "parsing error in line: `%s`" % line)
        else:
            try:
                yield PileupSubstitution( *[x(y) for x,y in zip(conv_subst,d) ] )
            except TypeError:
                raise SamtoolsError( "parsing error in line: `%s`" % line)
