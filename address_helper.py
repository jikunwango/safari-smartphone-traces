import math
import copy
import os
import utils.hex_utils as hu

"""
This tool script is for trace/address generation, validation and convert, before running you should be clear about
    @ What the page size? 4KB or 8KB, we currently consider 4KB as a page size both in OS and memory system
    @ what the density should OS map to? 8Gb -> 32K rows while 16Gb -> 64K rows
    @ We assume subarray size is 512
"""
# how many Gb in a chip, when density is 12 Gb, bit-14 is 0 when bit-15 is 1
g_mem_density = 12
# Page size, KB
g_page_size = 4
# how many rows in a subarray
g_subarray_size = 512
# how many column bits
g_column_bits = int(math.log2(g_page_size << 10))
# how many rows
g_total_rows = int((g_mem_density / 4) * (16 << 10))
# how many row bits
g_rows_bit = math.ceil(math.log2(g_total_rows))
g_bank_num = 8
g_bank_bits = int(math.log2(g_bank_num))
# prefetch bits size for each column
# g_prefetch_size = 8
g_prefetch_size = 16
# channel width
# g_channel_width = 64
g_channel_width = 16
# total bytes in a channel fetch
g_prefetch_bytes = g_prefetch_size * g_channel_width / 8
# bytes offset in a channel fetch
g_tx_offset = 6
# g_tx_offset = int(math.log2(g_prefetch_bytes))

# actual column index bits
# g_column_index_bits = g_column_bits - (g_tx_offset - int(math.log2(g_channel_width / 8)))
g_column_index_bits = g_column_bits - g_tx_offset

# this is a dram hierachy of 16-bits row and 10-bits column
# g_levels_mask_bits = [0, 1, 2, 2, 16, g_column_index_bits]
g_levels_mask_bits = [0, 0, g_bank_bits, g_rows_bit, g_column_index_bits]
# 10 plus 3, 10 bits stand for the block index, 3 bits stand for byte index within a block
# g_assemble_levels_bits = [0, 1, 2, 2, 16, 13]
g_assemble_levels_bits = [0, 0, g_bank_bits, g_rows_bit, g_column_bits]
g_row_level_index = len(g_assemble_levels_bits) - 2

# subarray mask bits, check whether two rows are in the same subarray
g_subarray_offset = int(
    math.log2(g_subarray_size) + g_assemble_levels_bits[g_row_level_index + 1]
)
# how many rows in a bank
g_rows_num_each_bank = g_total_rows
# how many subarrays in a bank
g_subarray_num = int(g_rows_num_each_bank / g_subarray_size)

g_bits_matters_mask = sum(g_assemble_levels_bits)


def print_mem_spec():
    spec_info = (
        "Memspec info:\n"
        "density is {}Gb \n"
        "page size is {}KB \n"
        "total banks is {} \n"
        "subarray size is {} \n"
        "total rows is {} \n"
        "subarray num in each bank is {} \n"
        "prefetch size is {} \n"
        "channel width is {} \n"
    ).format(
        g_mem_density,
        g_page_size,
        g_bank_num,
        g_subarray_size,
        g_total_rows,
        g_subarray_num,
        g_prefetch_size,
        g_channel_width,
    )
    print(spec_info)


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
def address_to_byte_level(addr: int) -> list[int]:
    address = addr & ((1 << g_bits_matters_mask) - 1)
    results = []
    for bits in g_assemble_levels_bits[::-1]:
        value = address & ((1 << bits) - 1)
        results.append(value)
        address >>= bits
    return results[::-1]


def mask_address(addr: int) -> int:
    return addr & ((1 << g_bits_matters_mask) - 1)


# assemble value from different levels to a physical address
def assemble_address(values):
    size = len(values)
    address: int = values[size - 1]
    current_bit_position = 0
    copy_list: list = copy.deepcopy(values)
    copy_list.pop(size - 1)
    copy_list.insert(0, -1)
    for bits, value in reversed(list(zip(g_assemble_levels_bits, copy_list))[1:]):
        current_bit_position += bits
        address |= value << current_bit_position
    return address


def save_to_file(array, file_path):
    directory = os.path.dirname(file_path)

    if directory and not os.path.exists(directory):
        os.makedirs(directory)

    with open(file_path, "w") as file:
        for line in array:
            file.write(str(line) + "\n")


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
        if addr_1 == -1 or addr_1 == -2:
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


def traces_array_to_block(traces, save_file: str):
    directory = os.path.dirname(save_file)
    if directory and not os.path.exists(directory):
        os.makedirs(directory)
    with open(save_file, "w") as file:
        for line in traces:
            file.write(convert_each_line(line) + "\n")


def address_files_to_byte_level(file_path: str):
    with open(file_path, "r") as file:
        for line in file:
            print(address_to_byte_level(int(line)))


def check_case_validity(case: list):
    for index, value in enumerate(case):
        if value < 0:
            raise ValueError("Value less than 0!")
        # if value > (2 << g_assemble_levels_bits[index]):
        #     raise ValueError("Out of range!")


def gen_virtual_traces(cases: list):
    results = []
    for case in cases:
        check_case_validity(case)
        address = assemble_address(case)
        # print(address)
        results.append(address)
    return results


g_cache_line_size = 64
g_cache_line_num_in_page = int((4 << 10) / g_cache_line_size)


# if we place all cache line in a bank/row
def gen_traces(physical_addr, swap_page_size, row_level_interleaving: bool):
    total_cache_line_num = int((swap_page_size << 10) / g_cache_line_size)
    page_num = int(swap_page_size / 4)
    # page_no = physical_addr >> 12
    src_bank_id = (physical_addr >> 28) & 7
    same_bank_cache_line_reqs = []
    # in same bank
    for i in range(0, page_num):
        for j in range(0, g_cache_line_num_in_page):
            same_bank_cache_line_reqs.append(
                [0, 0, src_bank_id, i, g_cache_line_size * j]
            )
    # in different banks 4 cache line in a bank
    bank_id = 0
    row_idx = 0
    already_placed_num = 0
    multiple_bank_cache_line_reqs = []
    bank_row_idx_map = dict.fromkeys(range(g_bank_num), 0)
    if row_level_interleaving:
        for i in range(0, page_num):
            bank_idx = (bank_id) % g_bank_num
            for j in range(0, g_cache_line_num_in_page):
                multiple_bank_cache_line_reqs.append(
                    [0, 0, bank_idx, bank_row_idx_map[bank_idx], j * g_cache_line_size]
                )
            bank_row_idx_map[bank_idx] += 1
            bank_id += 1
    else:
        for i in range(0, total_cache_line_num, 4):
            bank_idx = (bank_id) % g_bank_num
            multiple_bank_cache_line_reqs.append(
                [0, 0, bank_idx, row_idx, already_placed_num * g_cache_line_size]
            )
            multiple_bank_cache_line_reqs.append(
                [0, 0, bank_idx, row_idx, (already_placed_num + 1) * g_cache_line_size]
            )
            multiple_bank_cache_line_reqs.append(
                [0, 0, bank_idx, row_idx, (already_placed_num + 2) * g_cache_line_size]
            )
            multiple_bank_cache_line_reqs.append(
                [0, 0, bank_idx, row_idx, (already_placed_num + 3) * g_cache_line_size]
            )
            bank_id += 1
            if bank_id > 7:
                bank_id -= 8
                already_placed_num += 4
                if already_placed_num >= g_cache_line_num_in_page:
                    already_placed_num = 0
                    row_idx += 1
    # print(same_bank_cache_line_reqs)
    # for it in same_bank_cache_line_reqs:
    #     print(it)
    # print("************")
    # for itm in multiple_bank_cache_line_reqs:
    #     print(itm)
    # # print(multiple_bank_cache_line_reqs)
    return same_bank_cache_line_reqs, multiple_bank_cache_line_reqs


def convert_to_rowclone_trace(file_path: str):
    row_bits = g_assemble_levels_bits[5]
    subarray_mask_bits = g_assemble_levels_bits[5] + int(math.log2(g_subarray_size))
    traces = []
    row_clone_count = 0
    trace_line_count = 0
    with open(file_path, "r") as file:
        while file.readable():
            load_cmd = file.readline()
            store_cmd = file.readline()
            rd_addr = int(load_cmd.split()[1])
            wr_addr = int(load_cmd.split()[2])
            trace_line_count += 2
            # check if read and write are in the same subarray
            if rd_addr >> subarray_mask_bits == wr_addr >> subarray_mask_bits:
                # replace with a rowclone command
                traces.append("0 {} {}".format(rd_addr, wr_addr))
                row_clone_count += 1
            else:
                # split row request into 64 consecutive cache line request
                for cl in range(64):
                    rd_cl = (rd_addr >> row_bits) + (cl << g_tx_offset)
                    traces.append("0 {}".format(rd_cl))
                for cl in range(64):
                    wr_cl = (wr_addr >> row_bits) + (cl << g_tx_offset)
                    traces.append("0 -1 {}".format(wr_cl))
    with open("converted_case.trace", "w") as file:
        for line in traces:
            file.write(str(line) + "\n")
    return row_clone_count, trace_line_count


def gen_multiple_traces():
    g_swap_cases = [
        4,
        8,
        16,
        32,
        64,
        128,
        256,
        512,
        1024,
        2048,
        4096,
        8192,
        16384,
        32768,
    ]
    output_dir = "output/gen_traces/"
    for swap in g_swap_cases:
        case1, case2 = gen_traces(0, swap, True)
        save_to_file(case1, output_dir + "raw_block_consecutive_{}K.txt".format(swap))
        addr_res1 = gen_virtual_traces(case1)
        with open(output_dir + "mdc_consecutive_{}K.trace".format(swap), "w") as file:
            for pair in [[0, elem] for elem in addr_res1]:
                file.write(" ".join(map(str, pair)) + "\n")


# main()
gen_multiple_traces()
