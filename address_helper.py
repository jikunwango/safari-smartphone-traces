import math
import copy

"""
This tool script is for trace/address generation, validation and convert, before running you should be clear about
    @ What the page size? 4KB or 8KB, we currently consider 4KB as a page size both in OS and memory system
    @ what the density should OS map to? 8Gb -> 32K rows while 16Gb -> 64K rows
    @ We assume subarray size is 512
"""
# prefetch bits size for each column
# g_prefetch_size = 8
g_prefetch_size = 16
# channel width
# g_channel_width = 64
g_channel_width = 32
# total bytes in a channel fetch
g_prefetch_bytes = g_prefetch_size * g_channel_width / 8
# bytes offset in a channel fetch
g_tx_offset = int(math.log2(g_prefetch_bytes))
# actual column index bits
g_column_index_bits = 10 - (g_tx_offset - int(math.log2(g_channel_width / 8)))
# this is a dram hierachy of 16-bits row and 10-bits column
# g_levels_mask_bits = [0, 1, 2, 2, 16, g_column_index_bits]
g_levels_mask_bits = [0, 0, 3, 15, g_column_index_bits]
# 10 plus 3, 10 bits stand for the block index, 3 bits stand for byte index within a block
# g_assemble_levels_bits = [0, 1, 2, 2, 16, 13]
g_assemble_levels_bits = [0, 0, 3, 15, 12]
g_row_level_index = len(g_assemble_levels_bits) - 2
# how many rows in a subarray
g_subarray_size = 512
# subarray mask bits, check whether two rows are in the same subarray
g_subarray_offset = int(
    math.log2(g_subarray_size) + g_assemble_levels_bits[g_row_level_index + 1]
)
# how many rows in a bank
g_rows_num_each_bank = 2 ** g_assemble_levels_bits[g_row_level_index]
# how many subarrays in a bank
g_subarray_num = g_rows_num_each_bank / g_subarray_size


# convert physical address to dram hierachy level, considering tx_offset & channel width
def address_to_block_level(address: int) -> list[int]:
    results = []
    current_shift = 0
    address >>= g_tx_offset
    for level_bits in g_levels_mask_bits[::-1]:
        level_value = (address >> current_shift) & ((1 << level_bits) - 1)
        results.append(level_value)
        current_shift += level_bits
    return results[::-1]


# convert physical address to byte levels to specify a byte
def address_to_byte_level(address: int) -> list[int]:
    results = []
    for bits in g_assemble_levels_bits[::-1]:
        value = address & ((1 << bits) - 1)
        results.append(value)
        address >>= bits
    return results[::-1]


# assemble value from different levels to a physical address
def assemble_address(bit_counts, values):
    address: int = values[5]
    current_bit_position = 0
    copy_list: list = copy.deepcopy(values)
    copy_list.pop(5)
    copy_list.insert(0, -1)
    for bits, value in reversed(list(zip(bit_counts, copy_list))[1:]):
        current_bit_position += bits
        address |= value << current_bit_position
    return address


# validate instr format, check two addresses are in the same subarray
def convert_each_line(line: str):
    items = line.split()
    size = len(items)
    if size < 2 or size > 3:
        raise Exception("Error trace line: {}".format(line))
    bubble_count = int(items[0])
    if bubble_count < 0:
        raise Exception("Error bubble count: {}".format(line))
    addr_1 = int(items[1])
    addr_2 = -1
    mem_operation = "RD"
    if size == 3:
        addr_2 = int(items[2])
        if addr_1 == -1:
            mem_operation = "WR"
        else:
            mem_operation = "RC"
    result = "[{}]>{} {}"
    # convert
    if "RC" == mem_operation:
        # check two row are in the same subarray
        addr_1_block_levels = address_to_block_level(addr_1)
        addr_2_block_levels = address_to_block_level(addr_2)
        bank_1 = addr_1_block_levels[g_row_level_index - 1]
        bank_2 = addr_2_block_levels[g_row_level_index - 1]

        subarray_id_1 = (addr_1 >> g_subarray_offset) & (g_subarray_size - 1)
        subarray_id_2 = (addr_2 >> g_subarray_offset) & (g_subarray_size - 1)
        rc_result = (
            "[{}]>{} {} >> bank-sub-row [{},{},{}] to bank-sub-row [{},{},{}]".format(
                mem_operation,
                addr_1_block_levels,
                addr_2_block_levels,
                bank_1,
                subarray_id_1,
                addr_1_block_levels[g_row_level_index],
                bank_2,
                subarray_id_2,
                addr_2_block_levels[g_row_level_index],
            )
        )
        if bank_1 != bank_2:
            raise Exception(
                "Error: Row Clone, two addresses are not in same bank {} \n {}".format(
                    line, rc_result
                )
            )

        if subarray_id_1 != subarray_id_2:
            raise Exception(
                "Error: Row Clone, two addresses are not in the same subarray {}\n {}".format(
                    line, rc_result
                )
            )
        if (
            addr_1_block_levels[g_row_level_index]
            == addr_2_block_levels[g_row_level_index]
        ):
            raise Exception(
                "Error: Row Clone, two addresses are in the same row {} \n {}".format(
                    line, rc_result
                )
            )
        return rc_result
    else:
        address_block_levels = (
            address_to_block_level(int(items[2]))
            if mem_operation == "WR"
            else address_to_block_level(addr_1)
        )
        return result.format(mem_operation, address_block_levels, "")


def traces_file_to_block(file_path: str):
    with open(file_path, "r") as file:
        for line in file:
            print(convert_each_line(line))


def address_files_to_byte_level(file_path: str):
    with open(file_path, "r") as file:
        for line in file:
            print(address_to_byte_level(int(line)))


def check_case_validity(case: list):
    for index, value in enumerate(case):
        if value < 0:
            raise ValueError("Value less than 0!")
        if value > (2 << g_assemble_levels_bits[index]):
            raise ValueError("Out of range!")


def gen_virtual_traces(cases: list):
    for case in cases:
        check_case_validity(case)
        address = assemble_address(g_assemble_levels_bits, case)
        print(address)


# case for generating address, step by 64 bytes
# cases = [
#     [0, 0, 0, 1, 1, 0],
#     [0, 0, 0, 1, 2, 64],
#     [0, 0, 0, 1, 3, 128],
#     [0, 0, 0, 1, 4, 0],
#     [0, 0, 0, 1, 5, 0],
#     [0, 0, 0, 1, 6, 0],
#     [0, 0, 0, 1, 7, 0],
#     [0, 0, 0, 1, 8, 0],
# ]
# gen_virtual_traces(cases)

address_files_to_byte_level("address.txt")
traces_file_to_block("mobile_bf.trace")
