'''
Created on Nov 7, 2010

@author: mkiyer

chimerascan: chimeric transcript discovery using RNA-seq

Copyright (C) 2011 Matthew Iyer

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
'''
import logging
import collections
import shutil
import os

# local imports
from chimerascan import pysam
from chimerascan.lib.chimera import Chimera, DiscordantRead, \
    DiscordantTags, DISCORDANT_TAG_NAME, \
    OrientationTags, ORIENTATION_TAG_NAME
from chimerascan.lib.base import LibraryTypes

from chimerascan.pipeline.find_discordant_reads import get_gene_orientation

def parse_group_by_attr(myiter, attr):
    mylist = []
    prev = None
    for itm in myiter:
        cur = getattr(itm, attr)
        if prev != cur:
            if len(mylist) > 0:
                yield prev, mylist
                mylist = []
            prev = cur
        mylist.append(itm)
    if len(mylist) > 0:
        yield prev, mylist

def parse_sync_by_breakpoint(chimera_file, bam_file):
    # group reads by reference name (matches breakpoint name)
    bamfh = pysam.Samfile(bam_file, "rb")
    tid_rname_map = list(bamfh.references)
    # initialize iterator through reads
    read_iter = parse_group_by_attr(bamfh, "rname")
    read_iter_valid = True
    try:
        rname, reads = read_iter.next()
        read_breakpoint_name = tid_rname_map[rname]
    except StopIteration:
        bamfh.close()
        read_iter_valid = False
        reads = []
        read_breakpoint_name = "ZZZZZZZZZZZZZZ"
    # group chimeras by breakpoint name
    for chimera_breakpoint_name, chimeras in \
        parse_group_by_attr(Chimera.parse(open(chimera_file)), 
                            "breakpoint_name"):
        while (read_iter_valid) and (chimera_breakpoint_name > read_breakpoint_name):
            try:
                rname, reads = read_iter.next()
                read_breakpoint_name = tid_rname_map[rname]
            except StopIteration:
                read_iter_valid = False
                reads = []
        if chimera_breakpoint_name < read_breakpoint_name:
            yield chimeras, []
        else:
            yield chimeras, reads    
    bamfh.close()

def get_mismatch_positions(md):
    x = 0
    pos = []
    for y in xrange(len(md)):
        if md[y].isalpha():
            offset = int(md[x:y])
            pos.append(offset)
            x = y + 1
    return pos

def check_breakpoint_alignment(c, r,
                               anchor_min,
                               anchor_length,
                               anchor_mismatches):
    """
    returns True if read 'r' meets criteria for a valid
    breakpoint spanning read, False otherwise
    
    c - Chimera object
    r - pysam AlignedRead object
    """
    # get position of breakpoint along seq
    breakpoint_pos = len(c.breakpoint_seq_5p)
    # check if read spans breakpoint    
    if not (r.pos < breakpoint_pos < r.aend):
        return False   
    # calculate amount in bp that read overlaps breakpoint
    # and ensure overlap is sufficient
    left_anchor_bp = breakpoint_pos - r.pos
    if left_anchor_bp < max(c.homology_left, anchor_min):
        return False
    right_anchor_bp = r.aend - breakpoint_pos
    if right_anchor_bp < max(c.homology_right, anchor_min):
        return False
    # ensure that alignments with anchor overlap less than 'anchor_length'
    # do not have more than 'anchor_mismatches' mismatches in the 
    # first 'anchor_length' bases
    if min(left_anchor_bp, right_anchor_bp) < anchor_length:
        # find interval of smallest anchor
        if left_anchor_bp < anchor_length:
            anchor_interval = (0, left_anchor_bp)
        else:
            aligned_length = r.aend - r.pos
            anchor_interval = (aligned_length - right_anchor_bp, aligned_length)      
        # get positions where mismatches occur
        mmpos = get_mismatch_positions(r.opt('MD'))
        # see if any mismatches lie in anchor interval
        anchor_mm = [pos for pos in mmpos
                     if anchor_interval[0] <= pos < anchor_interval[1]]
        if len(anchor_mm) > anchor_mismatches:
            # too many mismatches within anchor position
            return False
    return True

def filter_spanning_reads(chimeras, reads, 
                          anchor_min, 
                          anchor_length, 
                          anchor_mismatches,
                          library_type):
    for i,r in enumerate(reads):
        if r.is_unmapped:
            continue
        # make a discordant read object
        # TODO: need to annotate reads elsewhere since they have already been sorted here
        r.tags = r.tags + [("HI", 0),
                           ("IH", 1),
                           ("NH", 1),
                           (DISCORDANT_TAG_NAME, DiscordantTags.DISCORDANT_GENE),
                           (ORIENTATION_TAG_NAME, get_gene_orientation(r, library_type))]
        dr = DiscordantRead.from_read(r)
        dr.is_spanning = True
        # check read alignment against chimeras
        for c in chimeras:
            if check_breakpoint_alignment(c, r, 
                                          anchor_min, 
                                          anchor_length, 
                                          anchor_mismatches):
                # valid spanning read
                yield c,dr

def merge_spanning_alignments(breakpoint_chimera_file,
                              encomp_bam_file,
                              singlemap_bam_file,
                              output_chimera_file,
                              anchor_min, 
                              anchor_length,
                              anchor_mismatches,
                              library_type,
                              tmp_dir):
    #
    # Process reads that are both encompassing and spanning
    #
    logging.debug("Processing encompassing/spanning reads")
    tmp_encomp_chimera_file = os.path.join(tmp_dir, "tmp_encomp_chimeras.bedpe")
    f = open(tmp_encomp_chimera_file, "w")
    filtered_hits = 0
    for chimeras, reads in parse_sync_by_breakpoint(breakpoint_chimera_file, encomp_bam_file):
        # build dictionary of chimera name -> qname -> discordant pairs
        chimera_qname_dict = collections.defaultdict(lambda: {})
        for c in chimeras:
            for dpair in c.encomp_frags:
                chimera_qname_dict[c.name][dpair[0].qname] = dpair        
        # find valid spanning reads
        for c, dr in filter_spanning_reads(chimeras, reads, 
                                           anchor_min, anchor_length, 
                                           anchor_mismatches, library_type):
            # ensure encompassing read is present
            if dr.qname not in chimera_qname_dict[c.name]:
                continue
            # get discordant pair
            dpair = chimera_qname_dict[c.name][dr.qname]
            # mark correct read (read1/read2) as a spanning read
            if dr.readnum == dpair[0].readnum:
                dpair[0].is_spanning = True
            elif dr.readnum == dpair[1].readnum:
                dpair[1].is_spanning = True
            else:
                assert False
            filtered_hits += 1
        # write chimeras back to file
        for c in chimeras:
            fields = c.to_list()
            print >>f, '\t'.join(map(str, fields))         
    f.close()
    logging.debug("\tFound %d hits" % (filtered_hits))
    #
    # Process reads that are single-mapped and spanning
    #
    logging.debug("Processing single-mapping/spanning reads")
    tmp_singlemap_chimera_file = os.path.join(tmp_dir, "tmp_singlemap_chimeras.bedpe")
    f = open(tmp_singlemap_chimera_file, "w")
    filtered_hits = 0
    for chimeras, reads in parse_sync_by_breakpoint(tmp_encomp_chimera_file, singlemap_bam_file):
        # find valid spanning reads
        for c, dr in filter_spanning_reads(chimeras, reads, 
                                           anchor_min, anchor_length, 
                                           anchor_mismatches, library_type):
            # ensure mate maps to 5' or 3' gene
            # TODO: implement this using sorted/indexed BAM file?
            # add read as a spanning read
            c.spanning_reads.append(dr)
            filtered_hits += 1            
        # write chimeras back to file
        for c in chimeras:
            fields = c.to_list()
            print >>f, '\t'.join(map(str, fields))                     
    f.close()
    logging.debug("\tFound %d hits" % (filtered_hits))
    # output_chimera_file    
    shutil.copyfile(tmp_singlemap_chimera_file, output_chimera_file)
    # remove temporary files
    if os.path.exists(tmp_encomp_chimera_file):
        os.remove(tmp_encomp_chimera_file)
    if os.path.exists(tmp_singlemap_chimera_file):
        os.remove(tmp_singlemap_chimera_file)
    

def main():
    from optparse import OptionParser
    logging.basicConfig(level=logging.DEBUG,
                        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")    
    parser = OptionParser("usage: %prog [options] <chimeras.breakpoint_sorted.txt> "
                          "<encomp.bam> <onemap.bam> <chimeras.out.txt>")
    parser.add_option("--anchor-min", type="int", dest="anchor_min", default=4)
    parser.add_option("--anchor-length", type="int", dest="anchor_length", default=8)
    parser.add_option("--anchor-mismatches", type="int", dest="anchor_mismatches", default=0)
    parser.add_option('--library', dest="library_type", 
                      default=LibraryTypes.FR_UNSTRANDED)
    options, args = parser.parse_args()
    breakpoint_chimera_file = args[0]
    encomp_bam_file = args[1]
    singlemap_bam_file = args[2]
    output_chimera_file = args[4]
    merge_spanning_alignments(breakpoint_chimera_file,
                              encomp_bam_file,
                              singlemap_bam_file,
                              output_chimera_file,
                              options.anchor_min, 
                              options.anchor_length,
                              options.anchor_mismatches,
                              options.library_type)

if __name__ == '__main__':
    main()
