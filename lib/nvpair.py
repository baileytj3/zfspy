"""
ZFSpy: zfs binding for python
Copyright (C) 2008 Chen Zheng <nkchenz@gmail.com>

This program can be distributed under the terms of the GNU GPL v2.
"""

import os
from struct import pack, unpack

DATA_TYPE = [
'DATA_TYPE_UNKNOWN',
'DATA_TYPE_BOOLEAN',
'DATA_TYPE_BYTE',
'DATA_TYPE_INT16',
'DATA_TYPE_UINT16',
'DATA_TYPE_INT32',
'DATA_TYPE_UINT32',
'DATA_TYPE_INT64',
'DATA_TYPE_UINT64',
'DATA_TYPE_STRING',
'DATA_TYPE_BYTE_ARRAY',
'DATA_TYPE_INT16_ARRAY',
'DATA_TYPE_UINT16_ARRAY',
'DATA_TYPE_INT32_ARRAY',
'DATA_TYPE_UINT32_ARRAY',
'DATA_TYPE_INT64_ARRAY',
'DATA_TYPE_UINT64_ARRAY',
'DATA_TYPE_STRING_ARRAY',
'DATA_TYPE_HRTIME',
'DATA_TYPE_NVLIST',
'DATA_TYPE_NVLIST_ARRAY',
'DATA_TYPE_BOOLEAN_VALUE',
'DATA_TYPE_INT8',
'DATA_TYPE_UINT8',
'DATA_TYPE_BOOLEAN_ARRAY',
'DATA_TYPE_INT8_ARRAY',
'DATA_TYPE_UINT8_ARRAY'
]

class StreamUnpack(object):
    """
    StreamUnpack is a handy way to unpack data to objects 

    Becareful not to exceed the boundaries of data

    Examples:    

        
    """

    def __init__(self, data): 
        """
        Instantiate a new StreamUnpack
            
        @data
            the data you want to parse
        
        Returns
            zfspy.StreamUnpack
        """
        self.endian = ''
        self.pos = 0  # always point to the next reading char
        self.data = data 
        self.len = len(data)

    def unpack(self, fmt, len):
        start = self.pos
        self.pos = self.pos + len
        return unpack(self.endian + fmt, self.data[start : start + len ])

    def boolean(self):
        if self.unpack('B', 1)[0]:
            return True
        else:
            return False

    def byte(self):
        return self.unpack('B', 1)[0]

    def int8(self):
        return self.unpack('b', 1)[0]

    def uint8(self):
        return self.unpack('B', 1)[0]

    def int16(self):
        return self.unpack('h', 2)[0]

    def uint16(self):
        return self.unpack('H', 2)[0]

    def int32(self):
        return self.unpack('i', 4)[0]

    def uint32(self):
        return self.unpack('I', 4)[0]

    def int64(self):
        return self.unpack('q', 8)[0]

    def uint64(self):
        return self.unpack('Q', 8)[0]

    def hrtime(self):
        return self.unpack('Q', 8)[0]

    def string(self):
        """
        Get a string from the stream, string is leading by its length

        @len
            length of the string. if len = 0, then find a string endwith a zero

        Returns
            String, with tail zeros striped
        """
        len = self.uint32()
        len = (len + 3) / 4 * 4 # align string
        start = self.pos
        self.pos = self.pos + len
        return self.data[start: start + len].strip('\x00')

    def rewind(self, offset):
        """
        Rewind pos of the stream

        @offset
            offset relative to current pos, backward postive, forward negative 

        Returns
            None
        """
        self.pos = self.pos - offset
        if self.pos < 0:
            self.pos = 0
        if self.pos > self.len:
            self.pos = len


    def eof(self):
        """
        Check end of stream
        
        Returns
            Bool
        """
        return self.pos == self.len
    
    def pf(self, len):
        """
        Print len Chars
        """
        for i in range(len):
            c = self.byte()
            if chr(c).isalpha():
                print self.pos-1, c, chr(c)
            else:
                print self.pos-1, c
        self.rewind(len)



class NVPair(object):
    """
    Unpack file or data to Dict.

    A xdr file is header + nvlist:

        header: one byte encoding, one byte endian, two more reserved

        nvlist:
            nvl_version    4
            nvl_flag       4

            The fllowing makes a pair, there maybe many pairs in a nvlist
                encoded_sz     4
                encoded_sz     4
                name length    4
                name string    
                data type      4
                elements number 4   
                data...The data can be nvlist too, so nvlist is recursive

            zeros ending   8

    Examples:

    """

    def __init__(self):
        self.su = None
        pass

    def unpack_file(self, file):
        """
        Unpack nvlist file to a dict

        @file

        Returns
            Dict
        """
        print file, '%d bytes' % os.stat(file).st_size
        return self.unpack(open(file, 'rb').read())


    def unpack(self, data):
        """
        Unpack nvlist format data to a dict

        @data
    
        Returns
            Dict
        """
        su = StreamUnpack(data)
        #Four bytes nvheader
        encoding = ['native', 'xdr'][su.byte()]
        endian = ['<', '>'][su.byte()]
        self.su = su
        self.su.endian = endian # Let StreamUnpacker care the enbian!
        self.su.rewind(-2) # skip two chars
        if encoding == 'native':
            print 'Native encoding not implement'
            return -1
        
        xdr = {}
        xdr['nvh_encoding'] = encoding
        xdr['nvh_endian'] = endian
        xdr['value'] = self._nvlist_decode()
        return xdr
    
    def _nvlist_end(self):
        # look ahead for 8 bytes nvlist endmark, eaten them if found
        i = self.su.uint64()
        if i == 0:
            return True
        else:
            self.su.rewind(8)
            return False
        pass

    def _nvlist_decode(self):
        nvl = {}
        nvl['version'] = self.su.uint32()
        nvl['flag'] = self.su.uint32()
        nvl['nvpairs'] = self._pairs_decode() 
        return nvl

    def _pairs_decode(self):
        # A nvlist may contain manys pairs, we should decode them all until
        # we found the endmark
        pairs = []
        while not self._nvlist_end():
            pairs.append(self._single_pair_decode())
        return pairs 
        
    def _single_pair_decode(self):
        #Get name, type, elements number
        pair = {}
        pair['encoded_sz'] = self.su.uint32()
        pair['decoded_sz'] = self.su.uint32()
        pair['name'] = self.su.string()
        
        type = self.su.uint32()
        n = self.su.uint32() 
        type = DATA_TYPE[type]
        # Adjust the elments number, only array type has more than one elements.
        # We did not check malformed file format here
        if type == 'DATA_TYPE_BOOLEAN':
            n = 0
            pair['value'] = None 
            return pair
        else:
            if 'ARRAY' not in type:
                n = 1

        pair['type'] = type 
        pair['elements_n'] = n
        value = []
        # It's wired thinking of nvlistarray, in memory I know how it looks like, 
        # but what about in a file? How to store nvlist's data?
        # Parse all the elements
        for i in range(n):
           value.append(self._elements_decode(type))

        # If there is only one value, we return it directly
        if n == 1:
            pair['value'] = value[0]
        else:
            pair['value'] = value
        return pair

    def _elements_decode(self, type):
        if 'NVLIST' in type:
            return self._nvlist_decode()
        # Thank python, here is the magic!
        attr = type.split('_')[2].lower()
        return getattr(self.su, attr)()


if __name__ == '__main__':
    np = NVPair()
    xdr_file = np.unpack_file('/etc/zfs/zpool.cache')

    from pprint import pprint
    
    nvl = xdr_file['value']
    print 'aha, found zpool: '
    for pool in nvl['nvpairs']:
        print pool['name']

    pprint(xdr_file)
        
