from __future__ import annotations

# yes this is hacky af, but it's just for examples
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import torch
from torchvision import datasets, transforms
from torch.utils.data import DataLoader
from torch import nn

from lemnos.shared import LockedShape, ShapeBound
from lemnos.schema import Schema, SchemaNode, New, Existing, PowerGrowth, LinearGrowth, BreedIndices
from lemnos.schema.components import Conv, BatchNorm, Softmax, ReLU, SiLU, Sum, GroupType, Full, LayerNorm, ChannelDropout
from lemnos.adapter.torch import TorchEvaluator, generate_source, Adam, SGD, StepLR 
from lemnos.control import or_search, AvgLossWindowSelector 

def main():
	if (ir := model_1().compile_ir([LockedShape(3, 32, 32)], BreedIndices(), 70)) is not None: #purely for demonstration purposes
		print(generate_source("Example", ir))
		#train_transform = transforms.Compose([transforms.ToTensor(), transforms.RandomHorizontalFlip(p=.5), transforms.RandomErasing(p=.4, scale=(.02, .2)), transforms.RandomVerticalFlip(p=.5)])
		train_transform = transforms.Compose([transforms.ToTensor(), transforms.RandomHorizontalFlip(p=.5)])

		train_data = datasets.CIFAR10('data', train=True, download=True, transform=train_transform)
		validation_data = datasets.CIFAR10('data', train=False, download=True, transform=transforms.ToTensor())

		train_loader = DataLoader(train_data, batch_size=64, shuffle=True, pin_memory=True, num_workers=1, persistent_workers=True, prefetch_factor=16)
		validation_loader = DataLoader(validation_data, batch_size=64, shuffle=False, pin_memory=True, num_workers=1, persistent_workers=True, prefetch_factor=16)

		accuracy_func = lambda x, y: (x.argmax(dim=1) == y).float().sum().item()
		evaluator = TorchEvaluator(train_loader, validation_loader, 5, nn.CrossEntropyLoss(), accuracy_func, Adam(0.0003), None, True)

		train_metrics, validation_metrics = evaluator.evaluate(ir)
		#model_pool = or_search(model_1(), evaluator, AvgLossWindowSelector(1024), 80, 3, 3) 
	else:
		print("Failed to compile schema")


def model_1() -> Schema:
	groups = 16 

	head_1 = SchemaNode(ShapeBound(48, None, None), None, None, Conv(3, 1), ReLU(), BatchNorm())
	head_2 = SchemaNode(ShapeBound(128, None, None), None, None, Conv(3, 1), ReLU(), BatchNorm())

	head_1.add_group(New(head_2, 0))

	accume = SchemaNode(ShapeBound(None, None, None), None, Sum(), None, None, BatchNorm() , debug_name="accume")
	skip = SchemaNode(ShapeBound(None, None, None), None, None, None, None, ChannelDropout(.4), debug_name="skip")
	downsample = SchemaNode(ShapeBound(None, (2, None), (2, None)), PowerGrowth(256, .7, .0), Sum(), Conv(2, 0, 2, 1, groups, mix_groups=True), SiLU(), BatchNorm(), debug_name="downsample")

	dw_3_point = SchemaNode(ShapeBound(None, None, None), LinearGrowth(2, .0), None, Conv(groups=groups, mix_groups=True), ReLU(), BatchNorm(), debug_name="dw_3_point")
	depthwise_3 = SchemaNode(ShapeBound(None, None, None), None, None, Conv(3, 1, 1, 1, GroupType.DEPTHWISE), ReLU(), BatchNorm(), debug_name="depthwise_3")
	dw_collect = SchemaNode(ShapeBound(None, None, None), None, None, Conv(groups=groups, mix_groups=True), None, BatchNorm(), debug_name="dw_collect")

	tail_1 = SchemaNode(ShapeBound(256, 1), None, None, Conv(2, 0), ReLU(), BatchNorm(), debug_name="tail_1")
	tail_2 = SchemaNode(ShapeBound(10, 1), None, None, Full(), Softmax(), None)

	head_2.add_group(New(skip, 1), New(dw_3_point, 0))

	dw_3_point.add_group(New(depthwise_3, 0))
	depthwise_3.add_group(New(dw_collect, 2))
	dw_collect.add_group(Existing(accume, 0))
	dw_collect.add_group(Existing(downsample, 0))
	skip.add_group(New(downsample, 3))
	skip.add_group(New(accume, 3))

	downsample.add_group(New(skip, 1), New(dw_3_point, 0))
	accume.add_group(New(skip, 1), New(dw_3_point, 0))

	accume.add_group(New(tail_1, 1))

	tail_1.add_group(New(tail_2, 1))

	return Schema([head_1], [tail_2])

def model_2() -> Schema:
	groups = 1 

	head_1 = SchemaNode(ShapeBound(32, None, None), None, None, Conv(3, 1), ReLU(), BatchNorm())
	head_2 = SchemaNode(ShapeBound(64, None, None), None, None, Conv(3, 1), ReLU(), BatchNorm())

	downsample = SchemaNode(ShapeBound(None, (2, None), (2, None)), PowerGrowth(128, .7, .0), Sum(), Conv(2, 0, 2, 1, groups, mix_groups=True), ReLU(), BatchNorm())

	conv_3 = SchemaNode(ShapeBound(None, None, None), None, None, Conv(3, 1, groups=groups, mix_groups=True), ReLU(), BatchNorm())

	tail_1 = SchemaNode(ShapeBound(128, 1), None, None, Conv(2, 0), ReLU(), BatchNorm())
	tail_2 = SchemaNode(ShapeBound(10, 1), None, None, Full(), Softmax(), None)

	head_1.add_group(New(head_2, 0))
	head_2.add_group(New(downsample, 0))

	downsample.add_group(New(conv_3, 0))
	conv_3.add_group(New(conv_3, 0))
	conv_3.add_group(New(downsample, 0))


	conv_3.add_group(New(tail_1, 0))
	tail_1.add_group(New(tail_2, 0))

	return Schema([head_1], [tail_2])

main()
