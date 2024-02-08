from __future__ import annotations

from src.shared.index import Index
from src.shared.shape import Shape, LockedShape, OpenShape, Bound, Range
from abc import ABC as Abstract, abstractmethod 
from typing import List, Tuple

class BaseParameters(Abstract):
	__slots__ = ["_shape_bounds", "_batch_norm", "_dropout", "_regularization"]
	def __init__(self, shape_bounds: Bound) -> None:
		self._shape_bounds: Bound = shape_bounds 
	def validate_output_shape(self, shape_in: LockedShape, shape_out: LockedShape) -> bool:
		return self.validate_output_shape_transform(shape_in, shape_out) and shape_out in self._shape_bounds
	@abstractmethod
	def validate_output_shape_transform(self, shape_in: LockedShape, shape_out: LockedShape) -> bool:
		pass
	def get_mould_and_output_shapes(self, mould_shape: LockedShape, output_conformance: Shape, index: Index = Index()) -> Tuple[LockedShape, LockedShape] | None:
		mould_shape = mould_shape.squash(self.dimensionality())
		output_shape = self._get_output_shape(mould_shape, output_conformance, index)
		return None if output_shape is None or output_shape not in self._shape_bounds else (mould_shape, output_shape)
	@abstractmethod
	def _get_output_shape(self, input_shape: LockedShape, output_conformance: Shape, index: Index = Index()) -> LockedShape | None:
		pass
	def dimensionality(self) -> int:
		return len(self._shape_bounds)
	
class IdentityParameters(BaseParameters):
	def __init__(self, shape_bounds: Bound) -> None:
		super().__init__(shape_bounds)
	def validate_output_shape_transform(self, shape_in: LockedShape, shape_out: LockedShape) -> bool:
		return shape_in == shape_out
	def _get_output_shape(self, input_shape: LockedShape, output_conformance: Shape, index: Index = Index()) -> LockedShape | None:
		return input_shape if output_conformance.compatible(input_shape) else None

def _fill_conv_tuple(val: Tuple | int, dimensionality: int) -> Tuple:
	return val if isinstance(val, tuple) else tuple([val] * (dimensionality - 1))
class ConvParameters(BaseParameters):
	__slots__ = ["_shape_bounds", "_size_coefficents", "_merge_method", "_kernel", "_stride", "_dilation", "_padding", "depthwise"]
	def __init__(self,
			shape_bounds: Bound, 
			size_coefficents: Range,
			kernel: Tuple | int = 1, 
			stride: Tuple | int = 1, 
			dilation: Tuple | int = 1,
			padding: Tuple | int = 0,
			depthwise: bool = False, #TODO: change this to a factor? or somthing else so filter groups can be a different size and a different number of groups
			) -> None:
		super().__init__(shape_bounds)
		if len(shape_bounds) < 2:
			raise Exception("shape_bounds must have at least two dimensions")
		self._size_coefficents = size_coefficents 
		self._kernel: Tuple = _fill_conv_tuple(kernel, len(shape_bounds))
		self._stride: Tuple = _fill_conv_tuple(stride, len(shape_bounds))
		self._dilation: Tuple = _fill_conv_tuple(dilation, len(shape_bounds))
		self._padding: Tuple = _fill_conv_tuple(padding, len(shape_bounds))
		if (len(self._kernel) != len(self._stride) 
		  		or len(self._stride) != len(self._dilation) 
		  		or len(self._dilation) != len(self._padding) 
		  		or len(self._padding) != len(self._shape_bounds) - 1):
			raise Exception("kernel, stride, dilation, padding must all have the same length and be one less than shape_bounds")
		self.depthwise: bool = depthwise
	def output_dim_to_input_dim(self, output_shape: LockedShape, i: int) -> int:
		i -= 1
		return (output_shape[i + 1] - 1) * self._stride[i] + (self._kernel[i] * self._dilation[i] - (self._dilation[i] - 1)) - self._padding[i] * 2
	def input_dim_to_output_dim(self, input_shape: LockedShape, i: int) -> int:
		i -= 1
		return ((input_shape[i + 1] + self._padding[i] * 2) - (self._kernel[i] * self._dilation[i] - (self._dilation[i] - 1))) // self._stride[i] + 1
	def _get_output_shape(self, input_shape: LockedShape, output_conformance: Shape, index: Index = Index()) -> LockedShape | None:
		open_shape = OpenShape([self.input_dim_to_output_dim(input_shape, i) for i in range(1, len(input_shape))])
		if output_conformance.compatible(open_shape): 
			if output_conformance.is_locked():
				return open_shape.to_locked(output_conformance.get_product() // open_shape.get_product())
			else:
				lower = int(input_shape.get_product() * self._size_coefficents.lower()) // output_conformance.get_product()
				upper = int(input_shape.get_product() * self._size_coefficents.upper()) // output_conformance.get_product()
				return open_shape.to_locked(self._shape_bounds.clamp_value(index.get_shuffled((lower, upper), 0) , 0))
		else:
			return None
	def validate_output_shape_transform(self, shape_in: LockedShape, shape_out: LockedShape) -> bool:
		i = 1
		while i < len(shape_out) and self.output_dim_to_input_dim(shape_out, i) == shape_in[i]:
			i += 1
		return i == len(shape_out) and (not self.depthwise or shape_out[0] == shape_in[0])



