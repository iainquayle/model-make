from __future__ import annotations

import torch
from torch import Size
from typing import List

from copy import deepcopy
from dataclasses import dataclass

from math import prod

from abc import ABC as Abstract, abstractmethod

class ConformanceShape:
	def __init__(self, dimensions: int, partial_shape: Size) -> None:
		if len(partial_shape) > dimensions:
			raise Exception("partial shape greater than dimensions")
		self.dimensions = dimensions
		self.partial_shape = partial_shape
	def fully_constrained(self) -> bool:
		return len(self.partial_shape) == self.dimensions
	def __eq__(self, other: ConformanceShape) -> bool:
		return self.dimensions == other.dimensions and self.partial_shape == other.partial_shape
	@staticmethod
	def reduce_collection(conformance_shapes: List[ConformanceShape]) -> ConformanceShape | None:
		#rules:
		#	if no remaining open dims
		#		dims to the right must be the same
		#		remaing dims to the left must be product the same
		#	if one constrained shape
		#		take it or fit the other to it
		#	if remaining open dims
		#		dims to the right must be the same
		if len(conformance_shapes) == 0:
			raise Exception("cannot reduce empty collection")
		else:
			reduced_shape = ConformanceShape(0, Size())
			for conformance_shape in conformance_shapes:
				small = reduced_shape
				big = conformance_shape
				if ((len(reduced_shape.partial_shape) > len(conformance_shape.partial_shape))
						or (len(reduced_shape.partial_shape) == len(conformance_shape.partial_shape) 
						and reduced_shape.dimensions > conformance_shape.dimensions)):
					small = conformance_shape
					big = reduced_shape
				shape_equivilence_cutoff = 0
				if len(small.partial_shape) == 0:
					reduced_shape = big 
				elif big.fully_constrained():
					if small.fully_constrained():
						shape_equivilence_cutoff = len(small.partial_shape) - 1
						if prod(small.partial_shape[:-shape_equivilence_cutoff]) != prod(big.partial_shape[:-shape_equivilence_cutoff]):
							return None
						reduced_shape = big
					else:
						shape_equivilence_cutoff = len(small.partial_shape)
						reduced_shape = big
				else:
					if small.fully_constrained():
						shape_equivilence_cutoff = len(small.partial_shape) - 1
						big_product = prod(big.partial_shape[:-shape_equivilence_cutoff])
						if big_product % small.partial_shape[0] != 0:
							return None
						reduced_shape = ConformanceShape(big.dimensions, Size([small.partial_shape[0] // big_product] + list(big.partial_shape))) 
					else:
						shape_equivilence_cutoff = len(small.partial_shape)
						reduced_shape = big
				if small.partial_shape[-shape_equivilence_cutoff:] != big.partial_shape[len(big.partial_shape) - shape_equivilence_cutoff:]:
					print(small.partial_shape[len(small.partial_shape) - shape_equivilence_cutoff:], big.partial_shape[len(big.partial_shape) - shape_equivilence_cutoff:])
					return None
			return deepcopy(reduced_shape) 
	

class MergeMethod(Abstract):
	#currently can only take shapes of a higher dimension or same
	#this could be changed by checking that the bottom dimension can be split into the lower dimensions of higher dimension sibling shapes
	#come to think of it, it may only be possible if restricted to a jump of 1 dimension 
	#	or vice versa, and new higher dimensions shapes lower dimensions produce the same size
	#		this would be harder, but the other way would be viable
	@abstractmethod
	def get_conformance_shape(self, sibling_shapes: List[Size], shape_bounds: Bound) -> ConformanceShape:
		pass
	@abstractmethod
	def get_total_merged_size(self, shapes: List[Size]) -> int:
		pass
	@abstractmethod
	def get_merge_src(self, registers: List[str]) -> str | None:
		pass
class Concat(MergeMethod):
	def get_conformance_shape(self, sibling_shapes: List[Size], shape_bounds: Bound) -> ConformanceShape:
		if len(sibling_shapes) == 0:
			return ConformanceShape(len(shape_bounds), Size())
		else:
			shape_list = list(sibling_shapes[0])
			copy_cutoff = len(shape_list) - len(shape_bounds) + 1
			shape_list = shape_list[copy_cutoff:]
			return ConformanceShape(len(shape_bounds), Size(shape_list))
	def get_total_merged_size(self, shapes: List[Size]) -> int:
		return sum([prod(shape) for shape in shapes])
	def get_merge_src(self, registers: List[str]) -> str | None:
		return f"torch.cat([{', '.join(registers)}], dim=1)"
class Add(MergeMethod):
	def get_conformance_shape(self, sibling_shapes: List[Size], shape_bounds: Bound) -> ConformanceShape:
		if len(sibling_shapes) == 0:
			return ConformanceShape(len(shape_bounds), Size())
		else:
			shape_list = list(sibling_shapes[0])
			copy_cutoff = len(shape_list) - len(shape_bounds) + 1
			shape_list = [prod(shape_list[:copy_cutoff])] + shape_list[copy_cutoff:]
			return ConformanceShape(len(shape_bounds), Size(shape_list))
	def get_total_merged_size(self, shapes: List[Size]) -> int:
		return prod(shapes[0])
	def get_merge_src(self, registers: List[str]) -> str | None:
		return f"{' + '.join(registers)}"

class Index:
	MAX_INDEX = 2**16 -1
	def __init__(self, index: int =0) -> None:
		self.set_index(index)
	def set_index(self, index: int) -> None:
		self.index = index % Index.MAX_INDEX
	def get_index(self, max_index: int) -> int:
		return self.index % max_index if max_index > 0 else 0
	def as_ratio(self) -> float:
		return self.index / Index.MAX_INDEX

class Bound:
	def __init__(self, lower: Size | List[int] | int = Size(), upper: Size | List[int] | int = Size()) -> None:
		lower = Size([lower]) if isinstance(lower, int) else Size(lower)
		upper = Size([upper]) if isinstance(upper, int) else Size(upper)
		if len(lower) != len(upper):
			raise Exception("bound dimensions do not match")
		for lower_bound, upper_bound in zip(lower, upper):
			if lower_bound > upper_bound:
				raise Exception("lower bound greater than upper")
		self.upper: Size = upper
		self.lower: Size = lower 
	def __contains__(self, shape: Size) -> bool:
		if len(shape) != len(self.lower):
			return False
		for lower_bound, upper_bound, i in zip(self.lower, self.upper, shape):
			if i < lower_bound or i > upper_bound:
				return False
		return True
	def __len__(self) -> int:
		return len(self.lower)
	def __str__(self) -> str:
		return f"Bound({self.lower}, {self.upper})"
	def __repr__(self) -> str:
		return str(self)

class Range:
	def __init__(self, lower: float = 1, upper: float = 1) -> None:
		if upper < lower:
			exit("upper smaller than lower bound")
		self.upper: float = upper
		self.lower: float = lower
	def difference(self) -> int | float:
		return self.upper - self.lower
	def from_index(self, index: Index, size: int) -> int:
		return int((self.lower * size) + index.get_index((int)(self.difference() * size)))
