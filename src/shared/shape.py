from __future__ import annotations

from torch import Size
from typing import List, Iterable, Tuple
from typing_extensions import Self
from copy import copy
from math import prod
from abc import ABC as Abstract, abstractmethod
#not extending:
#	size, as it is just tuple
#	tuple, because init doesnt play nice when adding other parameters, and makes manipulation harder
#TODO: probably want to optim some of this
#TODO: make a proper to src
#TODO: consider making more for loop implementing functions rather than slice, as it may perform better 
#rules:
#	if no remaining open dims
#		dims to the right must be the same, dims to the left must be prod the same
#	if one constrained shape
#		dims to right must be same, choose or fit the shape that is the correct size
#	if remaining open dims
#		dims to the right must be the same

#TODO: consider renaming locked to fixed, or sized
class Shape(Abstract):
	__slots__ = ("_shape", "_product_cache")
	def __init__(self, shape: Tuple[int, ...] | List[int] | Size) -> None:
		self._shape: List[int] = list(shape) if not isinstance(shape, List) else shape
		self._product_cache: int = prod(self._shape)
	@staticmethod
	@abstractmethod
	def new(*values: int) -> Shape:
		pass
	@abstractmethod
	def upper_length(self) -> int:
		pass
	def reverse_upper_equal(self, reverse_index: int, other: Shape) -> bool:
		for i in range(1, reverse_index + 1):
			if self._shape[-i] != other._shape[-i]:
				return False
		return True
	def reverse_lower_product(self, reverse_index: int) -> int:
		return prod(self._shape[:-reverse_index])
	@abstractmethod
	def dimensionality(self) -> int:
		pass
	def upper_compatible(self, other: Shape) -> bool:
		reverse_index = min(self.upper_length(), other.upper_length())
		return self.reverse_upper_equal(reverse_index, other)
	@abstractmethod
	def to_locked(self, dimension: int) -> LockedShape:
		pass
	@abstractmethod
	def to_open(self) -> OpenShape:
		pass
	@abstractmethod
	def squash(self, dimensionality: int) -> Shape:
		pass
	def compatible(self, other: Shape) -> bool:
		return self.common(other) is not None
	def is_locked(self) -> bool:
		return isinstance(self, LockedShape)
	def common_lossless(self, other: Shape) -> Shape | None:
		return self.common(other) if len(self) > len(other) or (len(self) == len(other) and self.dimensionality() > other.dimensionality()) else other.common(self)
	@abstractmethod
	def common(self, other: Shape) -> Shape | None:
		pass
	@staticmethod
	def reduce_common_lossless(shapes: Iterable[Shape]) -> Shape | None:
		shapes_iter = iter(shapes)
		common = next(shapes_iter, None)
		if common is None:
			raise Exception("cannot reduce empty collection")
		for shape in shapes_iter:
			common = common.common_lossless(shape)
			if common is None:
				return None
		return common
	@abstractmethod
	def to_tuple(self) -> Tuple[int, ...]:
		pass
	def __getitem__(self, index: int) -> int:
		return self._shape[index]
	def __len__(self) -> int:
		return len(self._shape)
	def __iter__(self) -> Iterable[int]:
		return iter(self._shape)
	@abstractmethod
	def __eq__(self, other: Self) -> bool:
		pass
	@abstractmethod
	def __copy__(self) -> Shape:
		pass
	def get_product(self) -> int:
		return self._product_cache

class LockedShape(Shape):
	def __init__(self, shape: Tuple[int, ...] | List[int] | Size) -> None:
		if len(shape) == 0:
			raise Exception("locked shape cannot be empty")
		super().__init__(shape)
	@staticmethod
	def new(*values: int) -> LockedShape:
		return LockedShape(values)
	def upper_length(self) -> int:
		return len(self) - 1
	def dimensionality(self) -> int:
		return len(self)
	def to_locked(self, dimension: int) -> LockedShape:
		return LockedShape(self._shape)
	def to_open(self) -> OpenShape:
		return OpenShape(self._shape[1:])
	def squash(self, dimensionality: int) -> LockedShape:
		if dimensionality > self.dimensionality():
			return copy(self) 
		else:
			return LockedShape([prod(self._shape[:-(dimensionality - 1)])] + self._shape[-(dimensionality - 1):])
	def common(self, other: Shape) -> Shape | None:
		common = copy(self)
		reverse_index = min(self.upper_length(), other.upper_length())
		if other.is_locked():
			if self.reverse_lower_product(reverse_index) != other.reverse_lower_product(reverse_index):
				return None
		elif self[0] % other.reverse_lower_product(reverse_index) != 0:
				return None
		return common if self.reverse_upper_equal(reverse_index, other) else None 
	def to_tuple(self) -> Tuple[int, ...]:
		return tuple(self._shape)
	def __eq__(self, other: Self) -> bool:
		return other is not None and isinstance(other, LockedShape) and self._shape == other._shape
	def __copy__(self) -> LockedShape:
		return LockedShape(self._shape)

class OpenShape(Shape):
	@staticmethod
	def new(*values: int) -> OpenShape:
		return OpenShape(values)
	def upper_length(self) -> int:
		return len(self)
	def dimensionality(self) -> int:
		return len(self) + 1
	def to_locked(self, dimension: int) -> LockedShape:
		return LockedShape([dimension] + self._shape)
	def to_open(self) -> OpenShape:
		return OpenShape(self._shape)
	def squash(self, dimensionality: int) -> OpenShape:
		if dimensionality > self.dimensionality():
			return copy(self)
		else:
			return OpenShape(self._shape[-(dimensionality - 1):])
	def common(self, other: Shape) -> Shape | None:
		common = copy(self)
		reverse_index = min(self.upper_length(), other.upper_length())
		if other.is_locked():
			other_product = other.reverse_lower_product(reverse_index)
			self_product = self.reverse_lower_product(reverse_index)
			if other_product % self_product != 0:
				return None
			common = self.to_locked(other_product // self_product)
		return common if self.reverse_upper_equal(reverse_index, other) else None 
	def to_tuple(self) -> Tuple[int, ...]:
		return tuple([-1] + self._shape)
	def __eq__(self, other: Self) -> bool:
		return other is not None and isinstance(other, OpenShape) and self._shape == other._shape
	def __copy__(self) -> OpenShape:
		return OpenShape(self._shape)

class Bound:
	_LOWER_INDEX = 0
	_UPPER_INDEX = 1
	__slots__ = ("_bounds")
	def __init__(self, bounds: List[Tuple[int, int] | None]= []) -> None:
		self._bounds: List[Tuple[int, int] | None] = bounds
		for i in range(len(bounds)):
			element = bounds[i]
			if element is not None:
				if element[Bound._LOWER_INDEX] > element[Bound._UPPER_INDEX]:
					bounds[i] = element[Bound._UPPER_INDEX], element[Bound._LOWER_INDEX]
				if element[Bound._LOWER_INDEX] <= 0:
					raise Exception("lower bound less than 1")
	def __getitem__(self, index: int) -> Tuple[int, int] | None:
		return self._bounds[index]
	def lower(self, index: int) -> int | None:
		element = self._bounds[index]
		return element[Bound._LOWER_INDEX] if element is not None else None
	def upper(self, index: int) -> int | None:
		element = self._bounds[index]
		return element[Bound._UPPER_INDEX] if element is not None else None
	def clamp(self, shape: Shape) -> Shape:
		if shape.dimensionality() > len(self._bounds):
			raise Exception("shape dimensionality greater than bounds")
		new_shape = copy(shape)
		for i in range(1, len(new_shape) + 1):
			new_shape._shape[-i] = self.clamp_value(new_shape[-i], -i)
		return new_shape
	def clamp_value(self, value: int, index: int) -> int:
		element = self._bounds[index]
		if element is not None:
			return min(element[Bound._UPPER_INDEX], max(element[Bound._LOWER_INDEX], value))
		else:
			return value
	def __contains__(self, shape: Shape) -> bool:
		for i in range(1, max(len(shape), len(self._bounds)) + 1):
			element = self._bounds[-i]
			if element is not None:
				if shape[-i] < element[Bound._LOWER_INDEX] or shape[-i] > element[Bound._UPPER_INDEX]:
					return False
		return True
	def __len__(self) -> int:
		return len(self._bounds)
	def __str__(self) -> str:
		return f"Bound({self._bounds})"
	def __repr__(self) -> str:
		return str(self)

class Range:
	def __init__(self, lower: float = 1, upper: float = 1) -> None:
		if upper < lower:
			exit("upper smaller than lower bound")
		self._upper: float = upper
		self._lower: float = lower
	def difference(self) -> int | float:
		return self._upper - self._lower
	def lower(self) -> float:
		return self._lower
	def upper(self) -> float:
		return self._upper
