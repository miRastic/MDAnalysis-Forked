# $Id$
# Neighbour searching in MDAnalysis. 
# Based on Biopython's Bio/PDB/NeighborSearch.py
# [Copyright (C) 2002, Thomas Hamelryck (thamelry@binf.ku.dk)]
# under the terms of the Biopython license.

"""Fast atom neighbor lookup using a KD tree (implemented in C++) --- :mod:`MDAnalysis.KDTree.NeighborSearch`
==================================================================================================================

If you know that you are using a specific selection repeatedly then it
may be faster to explicitly build the selection using the
AtomNeighborSearch class instead of using MDAnalysis selections.

Example:

  import MDAnalysis.KDTree.NeighborSearch as NS

  u = Universe(psf,dcd)
  water = u.selectAtoms('name OH2')
  protein = u.selectAtoms('protein')
   
  ns_w = NS.AtomNeighborSearch(water)
  solvation_shell = ns_w.search_list(protein,4.0)  # water oxygens within 4A of protein

"""

import numpy
from KDTree import KDTree
from MDAnalysis.core.AtomGroup import AtomGroup
try:
    set([])
except NameError:
    from sets import Set as set

entity_levels = ('A','R','S')

class CoordinateNeighborSearch(object):
    """
    This class can be used for two related purposes:

    1. To find all indices of a coordinate list within radius 
    of a given query position. 

    2. To find all indices of a coordinate list that are within 
    a fixed radius of each other.

    CoordinateNeighborSearch makes use of the KDTree C++ module, so it's fast.
    """
    def __init__(self, coordinates, bucket_size=10): ##, copy=True):
        """
        o list of N coordinates (Nx3 numpy array)
        o bucket_size - bucket size of KD tree. You can play around 
        with this to optimize speed if you feel like it.
        """
        # to Nx3 array of type float (required for the C++ code)
        ## (also force a copy by default and make sure that the array order is compatible
        ## with the C++ code)
        ##self.coords=numpy.array(coordinates,dtype=numpy.float32,copy=copy,order='C')
        self.coords=numpy.asarray(coordinates,dtype=numpy.float32,order='C')
        assert(self.coords.dtype == numpy.float32)
        assert(bucket_size>1)
        assert(self.coords.shape[1]==3)
        self.kdt=KDTree(3, bucket_size)
        self.kdt.set_coords(self.coords)
    
    def search(self, center, radius, distances=False):
        """Neighbor search.

        Return all indices in the coordinates list that have at least
        one atom within radius of center.

        o center - numpy array 
        o radius - float
        o distances - bool  True:  return (indices,distances)
                            False: return indices only
        """
        self.kdt.search(center, radius)
        if distances:
            return self.kdt.get_indices(), self.kdt.get_radii()
        else:
            return self.kdt.get_indices()

    def search_list(self, centers, radius):
        """Search neighbours near all centers.

        Returns all indices that are within radius of any center listed in
        centers, i.e. "find all A within R of B" where A are the
        coordinates used for setting up the CoordinateNeighborSearch and B
        are the centers.

        o centers - Mx3 numpy array of M centers
        o radius  - float
        """
        self.kdt.list_search(centers, radius)
        return self.kdt.list_get_indices()
            
    def search_all(self, radius, distances=False):
        """All neighbor search.

        Return all index pairs corresponding to coordinates within the radius.

        o radius - float
        o distances - bool  True:  return (indices,distances)
                            False: return indices only
        """
        self.kdt.all_search(radius)
        if distances:
            return self.kdt.all_get_indices(), self.kdt.all_get_radii()
        else:
            return self.kdt.all_get_indices()

    def _distances(self):
        """Return all distances after search()."""
        return self.kdt.get_radii()

    def _distances_all(self):
        """Return all distances after search_all()."""
        return self.kdt.all_get_radii()

class AtomNeighborSearch(CoordinateNeighborSearch):
    """
    This class can be used for two related purposes:

    1. To find all atoms/residues/segments within radius 
    of a given query position. 

    2. To find all atoms/residues/segments that are within 
    a fixed radius of each other.

    AtomNeighborSearch makes use of the KDTree C++ module, so it's fast.
    """
    def __init__(self, atom_list, bucket_size=10):
        """
        o atom_list - list of atoms. This list is used in the queries.
        It can contain atoms from different structures.
        o bucket_size - bucket size of KD tree. You can play around 
        with this to optimize speed if you feel like it.
        """
        self.atom_list=atom_list
        if not hasattr(atom_list,'coordinates'):
            raise TypeError('atom_list must have a coordinates() method '
                            '(eg a AtomGroup resulting from a Selection)')
        CoordinateNeighborSearch.__init__(self,atom_list.coordinates(),bucket_size=bucket_size)
    
    def search(self, center, radius, level="A"):
        """Neighbor search.

        Return all atoms/residues/segments
        that have at least one atom within radius of center.
        What entitity level is returned (e.g. atoms or residues)
        is determined by level (A=atoms, R=residues, S=Segments).

        o center - numpy array 
        o radius - float
        o level - char (A, R, S)
        """
        self.kdt.search(center, radius)
        indices=self.kdt.get_indices()
        return self._index2level(indices,level)

    def search_list(self, other, radius, level='A'):
        """Search neighbours near all atoms in atoms.

        Returns all atoms/residues/segments that contain atoms that are
        within radius of any other atom listed in other, i.e. "find all A
        within R of B" where A are the atoms used for setting up the
        AtomNeighborSearch and B are the other atoms.

        o other  - AtomGroup
        o radius - float
        o level  - char (A, R, S)
        """
        self.kdt.list_search(other.coordinates(), radius)
        indices=self.kdt.list_get_indices()
        return self._index2level(indices,level)
        
    def _index2level(self,indices,level):
        if not level in entity_levels:
            raise ValueError("%s: Unknown level" % level)
        n_atom_list = [self.atom_list[i] for i in indices]
        if level=="A":
            try:
                return AtomGroup(n_atom_list)
            except:
                return [] # empty n_atom_list (AtomGroup throws exception, can't be easily fixed...)
        elif level=="R":
            residues = set([a.residue for a in n_atom_list])
            return list(residues)
        elif level=="S":
            segments = set([a.segment for a in n_atom_list])
            return list(segments)
        else:
            raise NotImplementedError("level=%s not implemented" % level)
            
    def search_all(self, radius, level="A"):
        """All neighbor search.

        Search all entities that have atoms pairs within
        radius. 

        o radius - float
        o level - char (A, R, S)
        """
        if not level in entity_levels:
            raise ValueError("%s: Unknown level" % level)
        self.kdt.all_search(radius)
        indices=self.kdt.all_get_indices()
        atom_list=self.atom_list
        atom_pair_list=[]
        for i1, i2 in indices:
            a1=atom_list[i1]
            a2=atom_list[i2]
            atom_pair_list.append(AtomGroup([a1, a2]))
        if level=="A":
            return atom_pair_list  # return atoms as list of AtomGroup pairs
        elif level == "R":
            return self._get_unique_pairs('residue',atom_pair_list)
        elif level == "S":
            return self._get_unique_pairs('segment',atom_pair_list)
        else:
            raise NotImplementedError("level=%s not implemented" % level)

    def _get_unique_pairs(self,entity,atom_pair_list):
        # This is slow for large atom_pair_lists such as when doing entity='residues'.
        # use sets to remove duplicates:
        unique_pairs = set([
                sets.ImmutableSet((a1.__getattribute__(entity),
                                   a2.__getattribute__(entity)))
                for a1,a2 in atom_pair_list 
                if a1.__getattribute__(entity) != a2.__getattribute__(entity)])
        return [tuple(s) for s in unique_pairs]  # return as list of 2-tuples

def _test(x,y,z,R):
    """Find points of a 2x2 square (+origin) within R of x,y,z."""
    import numpy
    coords = numpy.array([ [0,0,0],
                           [1,1,0],
                           [-1,1,0],
                           [-1,-1,0],
                           [1,-1,0] ], dtype=numpy.float32)
    CNS = CoordinateNeighborSearch(coords)
    center = numpy.array([x,y,z])
    found_indices = CNS.search(center,R)
    # check manually
    diff = coords[found_indices] - center[numpy.newaxis,:]
    return found_indices,numpy.sqrt(numpy.sum(diff*diff, axis=1))

if __name__=="__main__":
    import numpy

    class Atom:
        def __init__(self):
            self.coord=100*numpy.random.random(3)
        def coordinates(self):
            return self.coord

    class AtomGroup(list):
        def coordinates(self):
            return numpy.array( [atom.coordinates() for atom in self] )

    for i in range(0, 20):
        al=AtomGroup([Atom() for i in range(0, 1000)])

        ns=AtomNeighborSearch(al)

        print "Found ", len(ns.search_all(5.0))


            

                
        
