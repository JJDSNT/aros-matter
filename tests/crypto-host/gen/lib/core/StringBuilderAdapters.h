// Stand-in: the pigweed string_builder adapters only pretty-print
// CHIP_ERROR in failed assertions; without them gtest prints bytes.
#pragma once
#include <pw_unit_test/framework.h>
#include <lib/core/CHIPError.h>
