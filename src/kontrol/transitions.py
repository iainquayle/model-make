from torch import Tensor, Size
from torch.nn import Module, ModuleList
from structures.commons import Identity, MergeMethod
from abc import ABC, abstractmethod
from typing import List, Set, Dict, Any, Tuple
from typing_extensions import Self
import gc
from copy import copy

class Bound:
	def __init__(self, lower: int | float =1, upper: int | float =1) -> None:
		if upper < lower:
			exit("upper smaller than lower bound")
		if upper < 0 or lower < 0:
			exit("bound in negative")
		self.upper: int | float = upper
		self.lower: int | float = lower 
	def inside(self, i: int | float) -> bool:
		return i >= self.lower and i <= self.upper	
class TransitionGroup:
	def __init__(self, transitions: Dict[Any, bool] =dict(), joining_transition: Any | None =None) -> None:
		self.transitions: Dict[Any, bool] = transitions	
		self.joining_transition: Any | None = joining_transition 
	def __str__(self) -> str:
		return f"TG {self.transitions} {self.joining_transition}"
	def __repr__(self) -> str:
		return str(self)
class SplitTreeNode:
	count = 0
	def __init__(self) -> None:
		self.splits: Dict[TransitionGroup, Tuple[Set[Transition], Self | None]] = dict() 
		self.id = str(SplitTreeNode.count)
		SplitTreeNode.count += 1
	def merge(self, other) -> Self:
		#for other_group, (other_transitions, other_next_node) in other.splits.items():
		merge_stack = [(x, y) for x, y in other.splits.items()]
		while len(merge_stack) > 0:
			other_group, (other_transitions, other_next_node) = merge_stack.pop()
			#TODO: whats the best solution for deletion and recurssive merging
			#also the self need to be checked for nodes to delete, so only looping on other is not sufficient when a graph has two entry points
			#this means merge stack wont work
			#can do iterative until no changes made, or can do recurssive merge on new self and new list of previously wrapped nodes now to be joined
			if other_group in self.splits:
				transitions, next_node = self.splits[other_group]
				self.splits[other_group] = (transitions | other_transitions, next_node)	
			else:
				self.splits[other_group] = (other_transitions, other_next_node)	
		return self
	def add(self, group, transition, next_node =None):
		self.splits[group] = ({transition}, copy(next_node))	
	def __copy__(self) -> Any:
		new_node = SplitTreeNode()
		for group, (transitions, next_node) in self.splits.items():
			new_node.splits[group] = (copy(transitions), copy(next_node))
		return new_node 
	def __str__(self) -> str:
		return f"STN{self.id} {self.splits}"	
	def __repr__(self) -> str:
		return str(self)	
class Transition:
	count = 0
	def __init__(self, 
	      shape_bounds: List[Bound] =[Bound()], 
			shape_coefficient_bounds: List[Bound] =[Bound()],
			activation_functions: List[Module] =[Identity()], 
			merge_method: MergeMethod =MergeMethod.ADD, 
			use_batch_norm: bool =True) -> None:
		self.next_state_groups: List[TransitionGroup] = [] 
		self.shape_bounds = shape_bounds 
		self.shape_coefficient_bounds = shape_coefficient_bounds
		self.activation_functions = activation_functions 
		self.merge_method = merge_method
		self.use_batch_norm = use_batch_norm 
		self.parents = dict()
		self.split_groups: Dict[TransitionGroup, Set[Transition]] = dict()
		self.id = Transition.count
		Transition.count += 1
	def add_next_state_group(self, group: TransitionGroup) -> None:
		self.next_state_groups.append(copy(group))
		self.analyse_splits()
	def analyse_splits(self, visits: Set[Self] = set()) -> None:
		#TODO: it may infact be completely necessary to make a stack of the splits
		#1. stack all splits behind new splits
		#2 add them to splits?
		#3 attempt to unwrap each, 		
		# - if split can be merged, unwrap, add to list(or just straight del)
		
		#this will make it such that if a transitions gives a split to itself
		#then gives that split to another split of its own, the first node in that split wont be able to tak credit
		#keep unwrapping until unable to  
		#there will be duplicates in a recurssive stack, however if those are already in the set then it doesnt matter

		#may also be from this that visits is no longer needed????

		#other option is to make node that recognises a group from self, force the merger, 
		#this may not be a good solution
		for group in self.next_state_groups:
			for state in group.transitions:
				if self in state.parents:
					state.parents[self].add(group)
				else:
					state.parents[self] = {group} 
		self.split_groups = dict()
		for parent, parent_group_set in self.parents.items():
			for parent_group in parent_group_set:
				self.split_groups[parent_group] = {self} 
			for split_group, transitions in parent.split_groups.items():
				if split_group in self.split_groups:
					self.split_groups[split_group] = self.split_groups[split_group] | transitions
				else:
					self.split_groups[split_group] = transitions
		groups_to_delete = set()
		for split_group, transitions in self.split_groups.items():
			if set(split_group.transitions) == transitions:
				split_group.joining_transition = self
				groups_to_delete.add(split_group)
			if split_group in self.next_state_groups:
				groups_to_delete.add(split_group)
		for group in groups_to_delete:
			self.split_groups.pop(group) 
		if self not in visits:
			for group in self.next_state_groups:
				for state in group.transitions:
					state.analyse_splits(visits | {self})
		gc.collect()
	@abstractmethod
	def get_function(self, index: int, shape_tensor: List[int] | Size) -> Module:
		pass
	def get_full_str(self) -> str:
		return f"{self}: ({self.next_state_groups})"
	def __str__(self) -> str:
		return f"T{self.id}"
	def __repr__(self) -> str:
		return str(self)

#TODO: consider making this purely an injectable piece
class ConvTransition(Transition):
	def __init__(self,  next_states=[], min_shape=[1], shape_coefficient_bounds=[1], max_concats=0, max_residuals=0) -> None:
		pass
	def get_function(self, index: int, mould_shape: List[int] | Size, shape_tensor: List[int] | Size):
		pass	
		pass