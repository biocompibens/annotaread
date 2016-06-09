#!/usr/bin/python
#-*- coding: utf-8 -*-

__author__ = 'noel & bahin'
''' <decription> '''

import argparse
import os
import numpy
import sys
import subprocess
import matplotlib.pyplot as plt
import matplotlib.cm as cmx
import matplotlib.colors as colors
import re
from matplotlib.backends.backend_pdf import PdfPages

##########################################################################
#                         FUNCTIONS                                      #
##########################################################################

def init_dict(d, key, init):
	if key not in d:
		d[key] = init

def get_chromosome_lengths(args):
	"""
	Parse the file containing the chromosomes lengths.
	If no length file is provided, browse the annotation file (GTF) to estimate the chromosome sizes (
	"""
	lengths={}
	gtf_chrom_names=set()
	force_get_lengths = False
	# If the user provided the chromosome length file
	if args.chr_len:
		with open(args.chr_len, 'r') as chr_len_file:
			for line in chr_len_file:
				lengths[line.split('\t')[0]] = int(line.rstrip().split('\t')[1])
		with open(args.annotation,'r') as gtf_file:
			for line in gtf_file:
				if not line.startswith('#'):
					chrom = line.split('\t')[0]
					if chrom not in gtf_chrom_names:
						gtf_chrom_names.add(chrom)
		for chrom in lengths.keys():
			if chrom not in gtf_chrom_names:
				print "Warning: at least one chromosome name ('"+chrom+"') of the file '"+args.chr_len+"'does not match any chromosome name if GTF and was ignored."
				#del lengths[chrom]
				break
		for chrom in gtf_chrom_names:
			if force_get_lengths: break
			if chrom not in lengths.keys():
				print "WARNING: chromosome name '"+chrom+"' was found in gtf and does not match any chromosome name provided in",args.chr_len+". "
				print "\t=> The chromosome lenghts will be approximated using annotations in the GTF file."
				continue_value =""
				while continue_value not in {"yes","y","no","n"}:
					continue_value = raw_input("\tDo you want to continue ('yes' or 'y')?\n\tElse write 'no' or 'n' to exit the script and check your file of lengths.\n")
					if continue_value == "no" or continue_value == "n":
						sys.exit("Exiting")
					elif continue_value == "yes" or continue_value == "y":
						force_get_lengths = True
						break
					print "Error: use 'yes/y/no/n' only"
		if not force_get_lengths:
			return lengths
	# Otherwise, (or if at least one chromosome was missing in chromosome lengths file) we consider the end of the last annotation of the chromosome in the GTF file as the chromosome length
	with open(args.annotation, 'r') as gtf_file:
		for line in gtf_file:
			if not line.startswith('#'):
				chrom = line.split('\t')[0]
				end = int(line.split('\t')[4])
				init_dict(lengths, chrom, 0)
				lengths[chrom] = max(lengths[chrom], end)
		if force_get_lengths:
			print "The chromosome lenghts have been approximated using the last annotations in the GTF file."
		return lengths

def write_feature_on_index(feat,chrom, start, stop, sign, stranded_genome_index, unstranded_genome_index=None):
	grouped_by_biotype_features = []
	for biotype,categs in feat.iteritems():
		categ_list=[]
		for cat in set(categs):
			categ_list.append(cat)
		grouped_by_biotype_features.append(":".join((str(biotype),",".join(categ_list))))
	stranded_genome_index.write('\t'.join((chrom, start, stop, sign,''))+'\t'.join(grouped_by_biotype_features)+'\n')
	if unstranded_genome_index :
		unstranded_genome_index.write('\t'.join((chrom, start, stop, '.',''))+'\t'.join(grouped_by_biotype_features)+'\n')


def add_info(cpt, feat_values, start, stop, chrom=None, unstranded_genome_index=None, stranded_genome_index = None , biotype_prios=None, coverage=1, categ_prios=None):
	"""
	From an annotated genomic interval (start/stop positions and associated feature : one or more category(ies)/biotype pair(s) )
	- If a file is provided: write the  information at the end of the index file being generated;
	- else : browse the features and update the counts of categories/biotypes found in the genome.
	"""
	## Writing in the file is it was provided
	if stranded_genome_index :
		unstranded_features = None
		# If only one strand has a feature, this feature will directly be written on the unstranded index
		if feat_values[0] == {} :
			# A interval with no feature corresponds to a region annotated only on the reverse strand : update 'antisense' counts
			stranded_genome_index.write('\t'.join((chrom, start, stop, '+','antisense\n')))
			write_feature_on_index(feat_values[1], chrom ,start, stop, '-', stranded_genome_index, unstranded_genome_index)
		else :
			if feat_values[1] == {} :
				write_feature_on_index(feat_values[0], chrom ,start, stop, '+', stranded_genome_index, unstranded_genome_index)
				stranded_genome_index.write('\t'.join((chrom, start, stop, '-','antisense\n')))
			
		# Else, the unstranded index should contain the union of plus and minus features
			else :
				write_feature_on_index(feat_values[0], chrom ,start, stop, '+', stranded_genome_index)
				write_feature_on_index(feat_values[1], chrom ,start, stop, '-', stranded_genome_index)
				unstranded_feat = dict(feat_values[0], **feat_values[1])
				for name in set(feat_values[0]) & set(feat_values[1]):
					unstranded_feat[name]+=feat_values[0][name]
				write_feature_on_index(unstranded_feat, chrom ,start, stop, '.', unstranded_genome_index)
	
	## Increasing category counter(s)
	else :
		# Default behavior if no biotype priorities : category with the highest priority for each found biotype has the same weight (1/n_biotypes)
		if not biotype_prios:
			nb_feat = len(feat_values)
			# For every categ(s)/biotype pairs
			for feat in feat_values:
				cur_prio = 0
				selected_categ = []
				# Separate categorie(s) and biotype
				try:
					biot,cats = feat.split(":")
				# Error if feature equal "antisense" : update the 'antisense/antisense' counts
				except ValueError :
					try :
						cpt[(feat,feat)] += (int(stop) - int(start)) * coverage / float(nb_feat) 
					except :
						cpt[(feat,feat)] = (int(stop) - int(start)) * coverage / float(nb_feat)
					return
				# Browse the categories and get only the one(s) with highest priority
				for cat in cats.split(','):
					try: prio = prios[cat]
					except:
						#TODO Find a way to add unknown categories
						if cat not in unknown_feature:
							print >> sys.stderr, "Warning : Unknown categorie %s found and ignored" %cat
							unknown_feature.append(cat)
						continue
					if prio > cur_prio :
						cur_prio = prio
						selected_categ = [cat]
					if prio == cur_prio :
						if cat != selected_categ :
							try:
								if cat not in selected_categ :
									selected_categ.append(cat)
							except TypeError :
								selected_categ = [selected_categ,cat]
				# Increase each counts by the coverage divided by the number of categories and biotypes
				nb_cats = len(selected_categ)
				for cat in selected_categ :
					try:
						cpt[(cat,biot)] += (int(stop) - int(start)) * coverage / (float(nb_feat * nb_cats))
					except KeyError:
						cpt[(cat,biot)] = (int(stop) - int(start)) * coverage / (float(nb_feat * nb_cats))
					#else :
						#cpt[(cats,biot)] = (int(stop) - int(start)) / float(nb_feat) * coverage
		# Else, apply biotype selection according to the priority set
		else:
			#TODO Add an option to pass biotype priorities and handle it
			pass

def print_chrom(features_dict, chrom, stranded_index_file, unstranded_index_file, cpt_genome):
	with open(unstranded_index_file,'a') as findex, open(stranded_index_file,'a') as fstrandedindex:
		# Initialization of variables : start position of the first interval and associated features for +/- strands
		start = ""
		for pos in sorted(features_dict['+'].keys()):
			if start != "":
				add_info(cpt_genome, [features_plus,features_minus], str(start), str(pos), chrom, stranded_genome_index = fstrandedindex, unstranded_genome_index = findex)
			start = pos
			features_plus = features_dict['+'][pos]
			features_minus = features_dict['-'][pos]


def create_genome_index(annotation, unstranded_genome_index, stranded_genome_index,cpt_genome,prios,biotypes,chrom_sizes):
	''' Create an index of the genome annotations and save it in a file'''
	print '\n### Generating genome indexes\n',
	sys.stdout.flush()
	# Initializations
	intervals_dict = 0
	max_value = -1
	prev_chrom = ''
	reverse_strand = {'+':'-','-':'+'}
	i = 0 # Line counter
	# Write the chromosomes lengths as comment lines before the genome index
	with open(unstranded_genome_index,'w') as findex, open(stranded_genome_index,'w') as fstrandedindex:
		for key,value in chrom_sizes.items():
			findex.write("#%s\t%s\n" %(key, value))
			fstrandedindex.write("#%s\t%s\n" %(key, value))
	# Running through the GTF file and writing into genome index files
	with open(annotation, 'r') as gtf_file:
		for line in gtf_file:
			# Print messages after X processed lines
			i += 1
			if i % 2000 == 0:
				print '.',
				sys.stdout.flush()
			if i % 20000 == 0:
				print '\r                          \r. . .',
				sys.stdout.flush()
			if i % 100000 == 0:
				print >> sys.stderr, str(i) + ' line processed...'
			# Processing lines except comment ones
			if not line.startswith('#'):
				# Getting the line infos
				line_split=line[:-1].split('\t')
				chrom = line_split[0]
				cat=line_split[2]
				start = int(line_split[3]) - 1
				stop = int(line_split[4])
				strand = line_split[6]
				antisense = reverse_strand[strand]
				biotype=line_split[8].split('biotype')[1].split(';')[0].strip('" ')
				feat = [(cat,biotype)]
				# Registering chromosome info in the genome index file if this is a new chromosome or a annotation not overlapping previously recorded features
				if start > max_value or chrom != prev_chrom: 
					# Write the previous features
					if intervals_dict != 0:
						if chrom != prev_chrom :
							print_chrom(intervals_dict, prev_chrom, stranded_genome_index, unstranded_genome_index, cpt_genome)
							print "\rChromosome '" + prev_chrom + "' registered."
						else:
							print_chrom(intervals_dict, chrom, stranded_genome_index, unstranded_genome_index, cpt_genome)
					prev_chrom = chrom
					# (Re)Initializing the chromosome lists
					intervals_dict = {strand:{start:{biotype:[cat]}, stop:{}},antisense:{start:{},stop:{}}}
					max_value = stop
					
				# Update the dictionary which represents intervals for every disctinct annotation 
				else:
					# Get intervals on the same strand as the current feature
					stranded_intervals = intervals_dict[strand]
					start_added = False
					for pos in sorted(stranded_intervals.keys()):
						#print pos
						#print stranded_intervals[pos]
						#print
						# While the position is below the feature's interval, store the features
						if pos < start :
							cur_cat_dict = dict(stranded_intervals[pos])
							cur_antisense_dict = dict(intervals_dict[antisense][pos])
							
						# If the start position already exists: update it by addind the new feature
						elif pos == start :
							cur_cat_dict = dict(stranded_intervals[pos])
							cur_antisense_dict = dict(intervals_dict[antisense][pos])
							#print "cur",cur_cat_dict
							try : stranded_intervals[pos][biotype] = stranded_intervals[pos][biotype]+[cat]
							except KeyError: stranded_intervals[pos][biotype] = [cat]
							start_added = True
							#print "cur",cur_cat_dict
							
						elif pos > start :
							# Create a new entry for the start position if necessary
							if not start_added :
								#print "cur",cur_cat_dict
								stranded_intervals[start] = dict(cur_cat_dict)
								stranded_intervals[start][biotype] = [cat]
								#stranded_intervals[pos][biotype].append(cat)
								intervals_dict[antisense][start] = cur_antisense_dict
								start_added = True
								#print "cur",cur_cat_dict
							# While the position is below the stop, just add the new feature
							if pos < stop :
								cur_cat_dict = dict(stranded_intervals[pos])
								cur_antisense_dict = dict(intervals_dict[antisense][pos])
								try: stranded_intervals[pos][biotype] = stranded_intervals[pos][biotype] + [cat]
								except KeyError: stranded_intervals[pos][biotype] = [cat]
							# Close the created interval : create an entry at the stop position and restore the features
							elif pos > stop :
								stranded_intervals[stop] = dict(cur_cat_dict)
								intervals_dict[antisense][stop] = cur_antisense_dict
								break
							else :
								break
						#try:
							#cur_cat_dict = list(stranded_intervals[pos][biotype])
						#except KeyError: cur_cat_dict = list()
						#print stranded_intervals[pos]
						#print
					# Extend the dictionary if necessary
					if stop > max_value:
						max_value = stop
						stranded_intervals[stop] = {}
						intervals_dict[antisense][stop] = {}
					#except KeyError:
						#print intervals_dict
						#quit()
						#intervals_dict[strand] = {strand:{start:{biotype:[cat]}, stop:{}},antisense:{start:{},stop:{}}}
						#continue
					#for sign in ['-','+']:
						#print sign
						#for key,val in sorted(intervals_dict[sign].iteritems()):
							#print key,'\t',val
						#print
					#print "-------\n"

								
		#Store the categories of the last chromosome
		print_chrom(intervals_dict, chrom, stranded_genome_index, unstranded_genome_index, cpt_genome)
		print "\rChromosome '" + prev_chrom + "' registered.\nDone!"


def create_bedgraph_files(bams,library_type):
	samples_files = []
	labels = []
	print "\n### Generating the bedgraph files"
	for n in range(0, len(bams), 2):
		print "Processing '%s'\n..." %bams[n],
		sys.stdout.flush()
		#Get the label for this sample
		label = bams[n+1]
		#Modify it to contain only alphanumeric caracters (avoid files generation with dangerous names)
		modified_label = "_".join(re.findall(r"[\w']+", label))
		if library_type in ["reverse","fr-secondstrand"]:
			subprocess.call('bedtools genomecov -bg -split -strand - -ibam ' + bams[n] + ' > ' + modified_label + '.plus.bedgraph', shell=True)
			subprocess.call('bedtools genomecov -bg -split -strand + -ibam ' + bams[n] + ' > ' + modified_label + '.minus.bedgraph', shell=True)
		elif library_type in ["forward","fr-firststrand"]:
			subprocess.call('bedtools genomecov -bg -split -strand + -ibam ' + bams[n] + ' > ' + modified_label + '.plus.bedgraph', shell=True)
			subprocess.call('bedtools genomecov -bg -split -strand - -ibam ' + bams[n] + ' > ' + modified_label + '.minus.bedgraph', shell=True)
		else :
			subprocess.call('bedtools genomecov -bg -split -ibam ' + bams[n] + ' > ' + modified_label + '.bedgraph', shell=True)
		samples_files.append(modified_label)
		labels.append(label)
	print "\rDone!"
	return samples_files, labels

def read_gtf(gtf_index_file, sign):
	global gtf_line, gtf_chrom, gtf_start, gtf_stop, gtf_features, endGTF
	strand = ""
	while strand != sign :
		gtf_line = gtf_index_file.readline()
		# If the GTF file is finished
		if not gtf_line:
			endGTF = True
			return endGTF
		splitline = gtf_line.rstrip().split('\t')
		try: strand = splitline[3]
		# strand information can not be found in the file file header
		except IndexError: pass
	gtf_chrom = splitline[0]
	gtf_features = splitline[4:]
	gtf_start, gtf_stop = map(int, splitline[1:3])
	return endGTF

def read_counts_files(counts_files):
	cpt={}
	cpt_genome={}
	labels=[]
	for fcounts in counts_files:
		label=os.path.splitext(os.path.basename(fcounts))[0]
		labels.append(label)
		cpt[label]={}
		with open (fcounts,"r") as f:
			for line in f:
				if line[0]=="#":
					continue
				line_split=line[:-1].split('\t')
				feature=tuple(line_split[0].split(','))
				cpt[label][feature]=float(line_split[1])
				cpt_genome[feature]=float(line_split[2])
	return cpt,cpt_genome,labels

def intersect_bedgraphs_and_index_to_counts_categories(samples_files,samples_names,prios,genome_index, library_type, biotype_prios = None):
	global gtf_line, gtf_chrom, gtf_start, gtf_stop, gtf_cat, endGTF
	print "\n### Intersecting files with indexes"
	cpt = {} # Counter for the nucleotides in the BAM input file(s)
	for n in range(len(samples_files)):
		sample_file=samples_files[n]
		sample_name=samples_names[n]
		# Initializing the category counter dict for this sample
		init_dict(cpt, sample_name, {})
		if library_type == "unstranded":
			strands = [("",".")]
		else:
			strands = [('.plus','+'), ('.minus','-')]
			
		# Intersecting the BEDGRAPH and genome index files
		print "Processing '%s'\n. . ." %sample_file,
		sys.stdout.flush()

		for strand,sign in strands:
			prev_chrom = ''
			endGTF = False # Reaching the next chr or the end of the GTF index
			intergenic_adds = 0.0
			i = 0
			i_chgt = 0
			with open(sample_file + strand + '.bedgraph', 'r') as bam_count_file:
				# Running through the BEDGRAPH file
				for bam_line in bam_count_file:
					i += 1
					if i % 10000 == 0:
						print ".",
						sys.stdout.flush()
					if i % 100000 == 0:
						print "\r                              \r. . .",
						sys.stdout.flush()
					# Getting the BAM line info
					bam_chrom = bam_line.split('\t')[0]
					bam_start, bam_stop, bam_cpt = map(float, bam_line.split('\t')[1:4])
					# If this is a new chromosome (or the first one)
					if bam_chrom != prev_chrom:
						i_chgt = i
						intergenic_adds = 0.0
						# (Re)opening the GTF index and looking for the first line of the matching chr
						try: gtf_index_file.close()
						except UnboundLocalError: pass
						gtf_index_file = open(genome_index, 'r')
						endGTF = False
						read_gtf(gtf_index_file, sign)
						while bam_chrom != gtf_chrom:
							read_gtf(gtf_index_file, sign)
							if endGTF:
								if strand == '.plus' or strand == "" :
									print "\r                          \r Chromosome '" + bam_chrom + "' not found in the GTF file."
								break
						prev_chrom = bam_chrom

					# Looking for the first matching annotation in the GTF index
					while (not endGTF) and (gtf_chrom == bam_chrom) and (bam_start >= gtf_stop):
						read_gtf(gtf_index_file, sign)
						if gtf_chrom != bam_chrom:
							endGTF = True
					# Processing BAM lines before the first GTF annotation if there are
					if bam_start < gtf_start:
						# Increase the 'intergenic' category counter with all or part of the BAM interval
						try:
							intergenic_adds += min(bam_stop,gtf_start)-bam_start
							cpt[sample_name][('intergenic','intergenic')] += (min(bam_stop, gtf_start) - bam_start) * bam_cpt
						except KeyError:
							cpt[sample_name][('intergenic','intergenic')] = (min(bam_stop, gtf_start) - bam_start) * bam_cpt
						# Go to next line if the BAM interval was totally upstream the first GTF annotation, carry on with the remaining part otherwise
						if endGTF or (bam_stop <= gtf_start):
							continue
						else:
							bam_start = gtf_start

					# We can start the crossover
					while not endGTF:
						# Update category counter
						add_info(cpt[sample_name], gtf_features, bam_start, min(bam_stop,gtf_stop), coverage = bam_cpt, categ_prios = prios)
						# Read the next GTF file line if the BAM line is not entirely covered
						if bam_stop > gtf_stop:
							# Update the BAM start pointer
							bam_start = gtf_stop
							endGTF = read_gtf(gtf_index_file, sign)
							# If we read a new chromosome in the GTF file then it is considered finished
							if bam_chrom != gtf_chrom:
								endGTF = True
							if endGTF:
								break
						else:
							# Next if the BAM line is entirely covered
							bam_start = bam_stop
							break

					# Processing the end of the BAM line if necessary
					if endGTF and (bam_stop > bam_start):
						try:
							cpt[sample_name][('intergenic','intergenic')] += (bam_stop - bam_start) * bam_cpt
						except KeyError:
							cpt[sample_name][('intergenic','intergenic')] = (bam_stop - bam_start) * bam_cpt
				gtf_index_file.close()
	print "\r                             \rDone!"
	return cpt

def write_counts_in_files(cpt,genome_counts):
	for label,dico in cpt.items():
		label = "_".join(re.findall(r"[\w']+", label))
		with open(label+".categories_counts","w") as fout:
			fout.write("#Category,biotype\tCounts_in_bam\tSize_in_genome\n" )
			for feature,counts in dico.items():
				fout.write("%s\t%s\t%s\n" %(','.join(feature),counts,genome_counts[feature]))

def recategorize_the_counts(cpt,cpt_genome,final):
	final_cat_cpt={}
	final_genome_cpt={}
	for f in cpt:
		#print "\nFinal categories for",f,"sample"
		final_cat_cpt[f]={}
		for final_cat in final:
			tot = 0
			tot_genome=0
			for cat in final[final_cat]:
					tot += cpt[f][cat]
					tot_genome+=cpt_genome[cat]
			#output_file.write('\t'.join((final_cat, str(tot))) + '\n')
			#print '\t'.join((final_cat, str(tot)))
			final_cat_cpt[f][final_cat]=tot
			final_genome_cpt[final_cat]=tot_genome
	return final_cat_cpt,final_genome_cpt

def group_counts_by_categ(cpt,cpt_genome,final,selected_biotype):
	final_cat_cpt={}
	final_genome_cpt={}
	filtered_cat_cpt = {}
	for f in cpt:
		final_cat_cpt[f]={}
		filtered_cat_cpt[f] = {}
		for final_cat in final:
			tot = 0
			tot_filter = 0
			tot_genome=0
			for cat in final[final_cat]:
					for key,value in cpt[f].items():
						if key[0] == cat :
							tot += value
							tot_genome+=cpt_genome[key]
							if key[1] == selected_biotype :
								tot_filter += value
			#output_file.write('\t'.join((final_cat, str(tot))) + '\n')
			#print '\t'.join((final_cat, str(tot)))
			final_cat_cpt[f][final_cat]=tot
			if tot_genome == 0:
				final_genome_cpt[final_cat]= 1e-100
			else:
				final_genome_cpt[final_cat]=tot_genome
			filtered_cat_cpt[f][final_cat]=tot_filter
	#if 'antisense' in final_genome_cpt: final_genome_cpt['antisense'] = 0
	return final_cat_cpt,final_genome_cpt,filtered_cat_cpt

def group_counts_by_biotype(cpt,cpt_genome,biotypes):
	final_cpt={}
	final_genome_cpt={}
	for f in cpt:
		final_cpt[f]={}
		for biot in biotypes:
			tot = 0
			tot_genome=0
			try:
				for final_biot in biotypes[biot]:
					for key,value in cpt[f].items():
						if key[1] == final_biot :
							tot += value
							#if key[1] != 'antisense':
							tot_genome+=cpt_genome[key]
			except:
				for key,value in cpt[f].items():
					if key[1] == biot :
						tot += value
						tot_genome+=cpt_genome[key]
			if tot != 0:
				final_cpt[f][biot]=tot
				final_genome_cpt[biot]=tot_genome
	return final_cpt,final_genome_cpt

#def get_cmap(N):
	#'''Returns a function that maps each index in 0, 1, ... N-1 to a distinct
	#RGB color.'''
	#color_norm  = colors.Normalize(vmin=0, vmax=N-1)
	#scalar_map = cmx.ScalarMappable(norm=color_norm, cmap='hsv')
	#def map_index_to_rgb_color(index):
		#return scalar_map.to_rgba(index)
	#return map_index_to_rgb_color

def one_sample_plot(ordered_categs, percentages, enrichment, n_cat, index, index_enrichment, bar_width, counts_type, title) :
	### Initialization
	fig = plt.figure(figsize=(13,9))
	ax1 = plt.subplot2grid((2,4),(0,0),colspan=2)
	ax2 = plt.subplot2grid((2,4),(1,0),colspan=2)
	cmap= plt.get_cmap('Spectral')
	cols=[cmap(x) for x in xrange(0,256,256/n_cat)]
	if title:
		ax1.set_title(title+"in: %s" %samples_names[0])
	else :
		ax1.set_title(counts_type+" distribution in mapped reads in: %s" %samples_names[0])
	ax2.set_title('Normalized counts of '+counts_type)

	
	### Barplots
	#First barplot: percentage of reads in each categorie
	ax1.bar(index, percentages, bar_width,
				color=cols)
	#Second barplot: enrichment relative to the genome for each categ
	# (the reads count in a categ is divided by the categ size in the genome)
	ax2.bar(index_enrichment, enrichment, bar_width,
				color=cols,)
	### Piecharts
	pielabels = [ordered_categs[i] if percentages[i]>0.025 else '' for i in xrange(n_cat)]
	sum_enrichment = numpy.sum(enrichment)
	pielabels_enrichment = [ordered_categs[i] if enrichment[i]/sum_enrichment>0.025 else '' for i in xrange(n_cat)]
	# Categories piechart
	ax3 = plt.subplot2grid((2,4),(0,2))
	pie_wedge_collection, texts = ax3.pie(percentages,labels=pielabels, shadow=True, colors=cols)
	# Enrichment piechart
	ax4 = plt.subplot2grid((2,4),(1,2))
	pie_wedge_collection, texts = ax4.pie(enrichment,labels=pielabels_enrichment, shadow=True, colors=cols)
	# Add legends (append percentages to labels)
	labels = [" ".join((ordered_categs[i],"({:.1%})".format(percentages[i]))) for i in range(len(ordered_categs))]
	ax3.legend(pie_wedge_collection,labels,loc='center',fancybox=True, shadow=True,prop={'size':'medium'}, bbox_to_anchor=(1.7,0.5))
	labels = [" ".join((ordered_categs[i],"({:.1%})".format(enrichment[i]/sum_enrichment))) for i in range(len(ordered_categs))]# if ordered_categs[i] != 'antisense']
	ax4.legend(pie_wedge_collection,labels,loc='center',fancybox=True, shadow=True,prop={'size':'medium'},bbox_to_anchor=(1.7,0.5))
	# Set aspect ratio to be equal so that pie is drawn as a circle
	ax3.set_aspect('equal')
	ax4.set_aspect('equal')
	return fig, ax1, ax2

def make_plot(ordered_categs,samples_names,categ_counts,genome_counts,pdf,counts_type,title = None):
	# From ordered_categs, keep only the features (categs or biotypes) that we can find in at least one sample.
	existing_categs = set()
	for sample in categ_counts.values():
		existing_categs |= set(sample.keys())
	ordered_categs = filter(existing_categs.__contains__, ordered_categs)
	n_cat = len(ordered_categs)
	n_exp=len(samples_names)
	##Initialization of the matrix of counts (nrow=nb_experiements, ncol=nb_categorie)
	counts=numpy.matrix(numpy.zeros(shape=(n_exp,n_cat)))
	for exp in xrange(len(samples_names)):
		for cat in xrange(len(ordered_categs)):
			try:	counts[exp,cat]=categ_counts[samples_names[exp]][ordered_categs[cat]]
			except:	pass

	##Normalize the categorie sizes by the total size to get percentages
	sizes=[]
	sizes_sum=0
	for cat in ordered_categs:
		sizes.append(genome_counts[cat])
		sizes_sum+=genome_counts[cat]
	if 'antisense' in ordered_categs:
		antisense_pos = ordered_categs.index('antisense')
		sizes[antisense_pos] = 1e-100
	for cpt in xrange(len(sizes)):
		sizes[cpt]/=float(sizes_sum)

	## Create array which contains the percentage of reads in each categ for every sample
	percentages=numpy.array(counts/numpy.sum(counts,axis=1))
	## Create the enrichment array (counts divided by the categorie sizes in the genome)
	enrichment=numpy.array(percentages/sizes)
	if 'antisense_pos' in locals(): 
		for i in xrange(len(samples_names)):
			enrichment[i][antisense_pos] = 0
	#enrichment=numpy.log(numpy.array(percentages/sizes))

	#### Finally, produce the plot

	##Get the colors from the colormap
	#cmap= plt.get_cmap('gist_ncar')
	cmap= plt.get_cmap('Spectral')
	cols=[cmap(i) for i in xrange(0,256,256/n_exp)]

	## Parameters for the plot
	opacity = 1
	#Create a vector which contains the position of each bar
	index = numpy.arange(n_cat)
	#Size of the bars (depends on the categs number)
	bar_width = 0.9/n_exp


	##Initialise the subplot
	# if there is only one sample, also plot piecharts 
	#if n_exp == 1 and counts_type.lower() == 'categories':
		#fig, ax1, ax2 = one_sample_plot(ordered_categs, percentages[0], enrichment[0], n_cat, index, bar_width, counts_type, title)
	## If more than one sample
	#else:
	fig, (ax1,ax2) = plt.subplots(2,figsize=(5+(n_cat+2*n_exp)/3,10))
	# Store the bars objects for enrichment plot
	rects = []
	#For each sample/experiment
	for i in range(n_exp):
		#First barplot: percentage of reads in each categorie
		ax1.bar(index+i*bar_width, percentages[i], bar_width,
					alpha=opacity,
					color=cols[i],
					label=samples_names[i])
		#Second barplot: enrichment relative to the genome for each categ
		# (the reads count in a categ is divided by the categ size in the genome)
		rects.append( ax2.bar(index+i*bar_width, enrichment[i], bar_width,
					alpha=opacity,
					color=cols[i],
					label=samples_names[i]))
		
	## Graphical options for the plot
	# Adding of the legend
	ax1.legend(loc='best',fancybox=True, shadow=True)
	# Main titles
	if title:
		ax1.set_title(title)
	else :
		ax1.set_title(counts_type+" distribution in mapped reads")
	ax2.set_title('Normalized counts of '+counts_type)
			
	# Change appearance of 'antisense' bars on enrichment plot since we cannot calculate an enrichment for this artificial category
	if 'antisense_pos' in locals(): #ax2.text(antisense_pos+bar_width/2,ax2.get_ylim()[1]/10,'NA')
		for i in xrange(n_exp) :
			rect = rects[i][antisense_pos]
			rect.set_height(ax2.get_ylim()[1]*1.2)
			rect.set_hatch('/')
			#rect.set_color('lightgrey')
			#rect.set_edgecolor('#EDEDED')
			rect.set_color('#EDEDED')
		ax2.text(index[antisense_pos] + bar_width*n_exp/2 - 0.1, ax2.get_ylim()[1]/2, 'NA')
	# Adding enrichment baseline
	ax2.axhline(y=1,color='black',linestyle='dashed',linewidth='1.5')
	# Axes limits
	ax1.set_xlim(-0.1,len(ordered_categs)+0.1)
	if len(sizes) == 1: ax1.set_xlim(-2,3) 
	ax2.set_xlim(ax1.get_xlim())
	ax1.set_ylim(ax1.get_ylim()[0]*1.05,ax1.get_ylim()[1]*1.05)
	ax2.set_ylim(ax2.get_ylim()[0]*1.05,ax2.get_ylim()[1]*1.05)
	# Y axis title
	ax1.set_ylabel('Proportion of reads (%)')
	ax2.set_ylabel('Enrichment relative to genome')
	# X axis title
	ax1.set_xlabel(counts_type)
	ax2.set_xlabel(counts_type)
	# Add the categories on the x-axis
	ax1.set_xticks(index + bar_width*n_exp/2)
	ax2.set_xticks(index + bar_width*n_exp/2)
	if counts_type.lower() != 'categories':
		ax1.set_xticklabels(ordered_categs,rotation='30',ha='right')
		ax2.set_xticklabels(ordered_categs,rotation='30',ha='right')
	else:
		ax1.set_xticklabels(ordered_categs)
		ax2.set_xticklabels(ordered_categs)

	#ax1.legend(loc='center right', bbox_to_anchor=(1.2, 0),fancybox=True, shadow=True)

	## Showing the plot
	plt.tight_layout()
	fig.subplots_adjust(wspace=0.2)
	
	if pdf:
		pdf.savefig()
		plt.close()
	else:
		plt.show()
	## Save on disk it as a png image 
	#fig.savefig('image_output.png', dpi=300, format='png', bbox_extra_artists=(lgd,), bbox_inches='tight')


def filter_categs_on_biotype(selected_biotype,cpt) :
	filtered_cpt = {}
	for sample in cpt:
		filtered_cpt[sample] = {}
		for feature,count in cpt[sample].items():
			if feature[1] == selected_biotype:
				filtered_cpt[sample][feature[0]] = count
	return filtered_cpt
	

##########################################################################
#                           MAIN                                         #
##########################################################################

def usage_message(name=None):                                                            
    return '''
    Generate genome indexes:
         annotaread.py -a GTF_FILE  [-g GENOME_INDEX]
                                         [--chr_len CHR_LENGTHS_FILE]
    Process BAM file(s):
         annotaread.py -g GENOME_INDEX -i BAM1 LABEL1 [BAM2 LABEL2 ...]
                                         [--bedgraph] [-t LIBRARY_TYPE]
                                         [-q] [-d {1,2,3,4}] [--pdf output.pdf]
    Index genome + process BAM:
         annotaread.py -a GTF_FILE [-g GENOME_INDEX]
                            -i BAM1 LABEL1 [BAM2 LABEL2 ...]
                            [--chr_len CHR_LENGTHS_FILE]
                            [--bedgraph][-t library_type]
                            [-q] [-d {1,2,3,4}] [--pdf output.pdf]
                            
    Process previously created PROG_NAME counts file(s):
         annotaread.py -c COUNTS1 [COUNTS2 ...]
                            [-t library_type]
                            [-q] [-d {1,2,3,4}] [--pdf output.pdf]

        '''



#### Parse command line arguments and store them in 'options'
parser = argparse.ArgumentParser(formatter_class=argparse.RawTextHelpFormatter, usage=usage_message())
parser.add_argument('--version', action='version', version='version 1.0', help="show program's version number and exit\n\n-----------\n\n")
# Options concernant l'index
parser.add_argument('-g','--genome_index', help="Genome index files path and basename for existing index, or path and basename for new index creation\n\n")
parser.add_argument('-a','--annotation', metavar = "GTF_FILE", help='Genomic annotations file (GTF format)\n\n')
parser.add_argument('--chr_len', help='Tabulated file containing chromosome names and lengths\n\n-----------\n\n')

# Options pour l'étape d'intersection
parser.add_argument('-i','--input','--bam', dest='input', metavar=('BAM_FILE1 LABEL1',""), nargs='+', help='Input BAM file(s) and label(s). The BAM files must be sorted by position.\n\n')
parser.add_argument('--bedgraph', action='store_const',default = False, const = True, help="Use this options if your input file(s) is(are) already in bedgraph format\n\n")
parser.add_argument('-c','--counts',metavar=('COUNTS_FILE',""), nargs='+', help="Use this options instead of '-i/--input' to provide PROG_NAME counts files as input \ninstead of bam/bedgraph files.\n\n")
parser.add_argument('-t','--library_type', nargs=1, action = 'store', default = ['unstranded'], choices = ['unstranded','forward','reverse','fr-firststrand','fr-secondstrand'], metavar="", help ="Library orientation. Choose within: 'unstranded', 'forward'/'fr-firststrand' \nor 'reverse'/'fr-secondstrand'. (Default: 'unstranded')\n\n-----------\n\n")
parser.add_argument('-s','--save_counts',action='store_const',default=True,const=True,help=argparse.SUPPRESS)#"Save the categories counts in current directory (label.categories_counts [label2.categories_counts ...])\n\n-----------\n\n")

# Options concernant le plot
parser.add_argument('-biotype_filter',nargs=1,help=argparse.SUPPRESS)#"Make an extra plot of categories distribution using only counts of the specified biotype.")
parser.add_argument('-d','--categories_depth', type=int, default='3', choices=range(1,5), help = "Depth of categories to be used (default=2): \n(1) gene,intergenic; \n(2) intron,exon,intergenic; \n(3) 5'UTR,CDS,3'UTR,intron,intergenic; \n(4) start_codon,5'UTR,CDS,3'UTR,stop_codon,intron,intergenic. \n\n")
parser.add_argument('--pdf', nargs='?', default=False, help="Save produced plots in specified path ('categories_plots.pdf' if no argument provided)\n\n")
parser.add_argument('-q', '--quiet', action='store_const', default=False, const=True, help="Do not show plots\n\n")

if len(sys.argv)==1:
    parser.print_usage()
    sys.exit(1)
    
options = parser.parse_args()


def required_arg(arg, aliases):
	if not arg:
		print >> sys.stderr, "\nError: %s argument is missing.\n" %aliases
		parser.print_usage()
		sys.exit()

def check_files_enxtension(files):
	return

# Booleans for steps to be executed
make_index = False
intersect_reads = False
process_counts = False

#### Check arguments conformity and define which steps have to be perfomed
if options.counts :
	# Aucun autre argument requis
	# Vérifier extension input
	
	# Action : Faire le plot uniquement
	process_counts = True
else:
	if options.annotation :
		# Vérifier si présence -gi
		#required_arg(options.genome_index,'-g/--genome_index')
		if options.genome_index :
			genome_index_basename = options.genome_index
		else:
			genome_index_basename = options.annotation.split("/")[-1].split(".gtf")[0]
		# Vérifier si un fichier existe déjà: 
		if os.path.isfile(genome_index_basename+".stranded.index") :
			if options.input:
				print >> sys.stderr, "\nWarning: a index file named %s already exists and will be used. If you want to create a new index, please delete this file or specify an other path." %(genome_index_basename+".stranded.index")
			else:
				sys.exit("\nError: a index file named %s already exists. If you want to create a new index, please delete this file or specify an other path.\n" %(genome_index_basename+".stranded.index"))
		# sinon -> action : index à faire
		else :
			make_index = True
	# si l'index n'est pas  à faire :
	if options.input:
		#	Arguments requis: input, genome_index
		if 'genome_index_basename' not in locals():
			required_arg(options.genome_index, "-g/--genome_index")
			genome_index_basename = options.genome_index
		required_arg(options.input, "-i/--input/--bam")
		for i in xrange(0, len(options.input), 2):
			try :
				extension = os.path.splitext(options.input[i+1])[1]
				if extension == ".bam" or extension == '.bedgraph' or extension == '.bg':
					sys.exit("Error: it seems input files and associated labels are not correctly provided.\n\
					Make sure to follow the expected format : -i Input_file1 Label1 [Input_file2 Label2 ...].")
			except:
				sys.exit("Error: it seems input files and associated labels are not correctly provided.\nMake sure to follow the expected format : -i Input_file1 Label1 [Input_file2 Label2 ...].")
		intersect_reads = True
	# Vérifier input's extension
	#TODO
if not (options.counts or options.input or options.annotation):
	sys.exit("\nError : some arguments are missing At least '-a', '-c' or '-i' is required. Please refer to help (-h/--help) and usage cases for more details.\n")
if not options.counts:
	# Declare genome_index variables
	stranded_genome_index = genome_index_basename+".stranded.index"
	unstranded_genome_index = genome_index_basename+".unstranded.index"
	if options.library_type[0] == "unstranded":
		genome_index = unstranded_genome_index
	else:
		genome_index = stranded_genome_index



#### Initialization of some variables

# Initializing the category priority order, coding biotypes and the final list
prios = {'start_codon': 7, 'stop_codon': 7, 'five_prime_utr': 6, 'three_prime_utr': 6, 'UTR': 6, 'CDS': 5, 'exon': 4, 'transcript': 3, 'gene': 2, 'antisense': 1,'intergenic': 0}

biotype_prios = None
#biotype_prios = {"protein_coding":1, "miRNA":2}

# Possibles groups of categories to plot
categs_group1={'start': ['start_codon'], '5UTR': ['five_prime_utr','UTR'], 'CDS': ['CDS', 'exon'], '3UTR': ['three_prime_utr'], 'stop': ['stop_codon'], 'introns': ['transcript', 'gene'], 'intergenic': ['intergenic'], 'antisense': ['antisense']}
categs_group2={'5UTR': ['five_prime_utr', 'UTR'], 'CDS': ['CDS', 'exon','start_codon','stop_codon'], '3UTR': ['three_prime_utr'], 'introns': ['transcript', 'gene'], 'intergenic': ['intergenic'], 'antisense': ['antisense']}
categs_group3={'exons': ['five_prime_utr', 'three_prime_utr', 'UTR', 'CDS', 'exon','start_codon','stop_codon'], 'introns': ['transcript', 'gene'], 'intergenic': ['intergenic'], 'antisense': ['antisense']}
categs_group4={'gene': ['five_prime_utr', 'three_prime_utr', 'UTR', 'CDS', 'exon','start_codon','stop_codon', 'transcript', 'gene'], 'intergenic': ['intergenic'], 'antisense': ['antisense']}
categs_groups = [categs_group4,categs_group3,categs_group2,categs_group1] # Order and merging for the final plot
cat_list = ['5UTR', 'start', 'CDS', 'stop', '3UTR', 'exons', 'introns', 'gene', 'intergenic', 'antisense']


# biotypes list
biotypes ={'protein_coding','polymorphic_pseudogene','TR_C_gene','TR_D_gene','TR_J_gene','TR_V_gene','IG_C_gene','IG_D_gene','IG_J_gene','IG_V_gene',"3prime_overlapping_ncrna","lincRNA","macro_lncRNA","miRNA","misc_RNA","Mt_rRNA","Mt_tRNA","processed_transcript","ribozyme","rRNA","scaRNA","sense_intronic","sense_overlapping","snoRNA","snRNA","sRNA","TEC","vaultRNA","antisense","transcribed_processed_pseudogene","transcribed_unitary_pseudogene","transcribed_unprocessed_pseudogene","translated_unprocessed_pseudogene","TR_J_pseudogene","TR_V_pseudogene","unitary_pseudogene","unprocessed_pseudogene","processed_pseudogene","IG_C_pseudogene","IG_J_pseudogene","IG_V_pseudogene","pseudogene","ncRNA","tRNA"} # Type: set (to access quickly)

# Grouping of biotypes:
biotypes_group1={'protein_coding':['protein_coding'],'pseudogenes':['polymorphic_pseudogene',"transcribed_processed_pseudogene","transcribed_unitary_pseudogene","transcribed_unprocessed_pseudogene","translated_unprocessed_pseudogene","TR_J_pseudogene","TR_V_pseudogene","unitary_pseudogene","unprocessed_pseudogene","processed_pseudogene","IG_C_pseudogene","IG_J_pseudogene","IG_V_pseudogene","pseudogene"],'TR':['TR_C_gene','TR_D_gene','TR_J_gene','TR_V_gene'],'IG':['IG_C_gene','IG_D_gene','IG_J_gene','IG_V_gene'],\
	'MT_RNA':["Mt_rRNA","Mt_tRNA"],\
	'ncRNA':["lincRNA","macro_lncRNA","3prime_overlapping_ncrna","ncRNA"],\
	"others":["misc_RNA","processed_transcript","ribozyme","scaRNA","sense_intronic","sense_overlapping","TEC","vaultRNA"],
	"antisense":["antisense"]}
for biot in ["miRNA","snoRNA","snRNA","rRNA","sRNA","tRNA"]:
	biotypes_group1[biot]=[biot]

# # Initializing the unkown features lits
unknown_feature = []

# Initializing the genome category counter dict
cpt_genome = {}


if process_counts :
	#### If input files are the categories counts, just load them and continue to recategorization step
	cpt,cpt_genome,samples_names = read_counts_files(options.counts)
else:
	#### Create genome index if needed and get the sizes of categories
	if make_index :
		#### Get the chromosome lengths
		lengths = get_chromosome_lengths(options)
		# Generating the genome index files if the user didn't provide them
		create_genome_index(options.annotation, unstranded_genome_index, stranded_genome_index, cpt_genome, prios, biotypes, lengths)


	#print '\nChr lengths:', lengths

if intersect_reads:
	# If the indexes already exist, read them to compute the sizes of the categories in the genome and retrieve the chromosome lengths
	if not make_index :
		print "\n### Reading genome indexes\n...",
		sys.stdout.flush()
	lengths={}
	with open(genome_index, 'r') as genome_index_file:
		for line in genome_index_file:
			if line[0] == "#":
				lengths[line.split('\t')[0][1:]] = int(line.split('\t')[1])
			else :
				add_info(cpt_genome, line.rstrip().split('\t')[4:], line.split('\t')[1], line.split('\t')[2], biotype_prios = None, categ_prios = prios)
						
	#### Computing the genome intergenic count: sum of the chr lengths minus sum of the genome annotated intervals
	cpt_genome[('intergenic','intergenic')] = sum(lengths.itervalues()) - sum([v for x,v in cpt_genome.iteritems() if x != ('antisense','antisense')])
	if not make_index :
		print "\rDone!"
	#print '\nGenome category counts:'
	#for key,val in cpt_genome.iteritems():
		#print key,"\t",val


	#### Create the Bedgraph files if needed and get the files list

	if not options.bedgraph:
		# Generating the BEDGRAPH files is the user provided BAM file(s) and get the samples labels (this names will be used in the plot legend)
		samples_files, samples_names = create_bedgraph_files(options.input,options.library_type[0])
	else:
		# Just initialize the files list with the bedgraph paths
		samples_files = [options.input[i] for i in range(0,len(options.input),2)]
		# and get the labels
		samples_names = [options.input[i] for i in range(1,len(options.input),2)]

	#### Processing the BEDGRAPH files: intersecting the bedgraph with the genome index and count the number of aligned positions in each category
	cpt = intersect_bedgraphs_and_index_to_counts_categories(samples_files,samples_names,prios,genome_index, options.library_type[0], biotype_prios = None)

	#### Write the counts on disk
	if options.save_counts:
		write_counts_in_files(cpt,cpt_genome)

if not (intersect_reads or process_counts) :
	quit()
print "\n### Generating plots"
# Updating the biotypes lists (biotypes and 'biotype_group1'): adding the 'unknow biotypes' found in gtf/index
if unknown_feature == []: # 'unknown_feature' is define only during the index generation
	# Browse the feature to determine whether some biotypes are 'unknown'
	for sample,counts in cpt.items():
		for (cat,biot) in counts:
			if biot not in biotypes and cat not in unknown_feature:
				unknown_feature.append(biot)
for new_biot in unknown_feature:
	biotypes.add(new_biot)
	biotypes_group1["others"].append(new_biot)
biotypes = sorted(biotypes)
# move antisense categ to the end of the list
biotypes.remove('antisense')
biotypes.append('antisense')
biotypes_group1 = sorted(biotypes_group1)


#print '\nCounts for every category/biotype pair: ',cpt

# Generating plots
if options.pdf != False:
	if options.pdf == None:
		options.pdf = "categories_plots.pdf"
	pdf = PdfPages(options.pdf)
else:
	pdf = False

selected_biotype = None
if options.biotype_filter:
	options.biotype_filter = options.biotype_filter[0]
	for sample in cpt:
		for feature in cpt[sample]:
			biotype = feature[1]
			if options.biotype_filter.lower() == biotype.lower():
				selected_biotype=biotype
				break
	if selected_biotype == None :
		print "\nError: biotype '"+options.biotype_filter+"' not found. Please check the biotype name and that this biotype exists in your sample(s)."
		sys.exit()

#Print a warning message if the UTRs are not specified as 5' or 3' (they will be ploted as 5'UTR)
if 'UTR'  in [categ[0] for counts in cpt.values() for categ in counts.keys()]:
	print '''\nWARNING : (some) 5'UTR/3'UTR are not precisely defined. Consequently, positions annotated as "UTR" will be counted as "5'UTR"\n'''

#### Make the plot by categories
	#### Recategorizing with the final categories
final_cats=categs_groups[options.categories_depth-1]
final_cat_cpt,final_genome_cpt, filtered_cat_cpt = group_counts_by_categ(cpt,cpt_genome,final_cats,selected_biotype)
	#### Display the distribution of specified categories (or biotypes) in samples on a barplot
# Remove the 'antisense' category if the library type is 'unstranded'
for dic in cpt.values():
	if ('antisense','antisense') in dic.keys(): break
else:
	cat_list.remove('antisense')
if not options.quiet or options.pdf:
	make_plot(cat_list,samples_names,final_cat_cpt,final_genome_cpt,pdf,"Categories")
if selected_biotype and(not options.quiet or options.pdf):
	make_plot(cat_list,samples_names,filtered_cat_cpt,final_genome_cpt,pdf,"Categories",title="Categories distribution for '"+selected_biotype+"' biotype")

#### Make the plot by biotypes
	#### Recategorizing with the final categories
final_cat_cpt,final_genome_cpt = group_counts_by_biotype(cpt,cpt_genome,biotypes)
	#### Display the distribution of specified categories (or biotypes) in samples on a barplot
if not options.quiet or options.pdf:
	make_plot(biotypes,samples_names,final_cat_cpt,final_genome_cpt,pdf,"Biotypes")



	##### Recategorizing with the final categories
#final_cat_cpt,final_genome_cpt = group_counts_by_biotype(cpt,cpt_genome,biotypes_group1)
	##### Display the distribution of specified categories (or biotypes) in samples on a barplot
#make_plot(biotypes_group1,samples_names,final_cat_cpt,final_genome_cpt,pdf,"Biotype groups",title="Biotypes distribution in mapped reads \n(biotypes are grouped by 'family')")


if options.pdf:
	pdf.close()
	print "\nPlots saved in pdf file : %s" %options.pdf
	
print "\n### End of program"