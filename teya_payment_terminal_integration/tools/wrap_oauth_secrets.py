#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vendor tool: wrap OAuth values with head/tail noise for teya_oauth_secrets.py"""
import argparse
import random
import string
import sys

HEAD = TAIL = 10


def _noise(n):
    return "".join(random.choices(string.ascii_letters + string.digits, k=n))


def wrap(core, head=None, tail=None):
    head = head or _noise(HEAD)
    tail = tail or _noise(TAIL)
    if len(head) != HEAD or len(tail) != TAIL:
        raise ValueError(f"head and tail must be exactly {HEAD} characters")
    return head + core + tail


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--alpha", required=True, help="Core value for PARTNER_REF_ALPHA")
    parser.add_argument("--beta", required=True, help="Core value for PARTNER_REF_BETA")
    args = parser.parse_args()
    alpha = wrap(args.alpha)
    beta = wrap(args.beta)
    print(f"PARTNER_REF_ALPHA = '{alpha}'")
    print(f"PARTNER_REF_BETA = '{beta}'")
    print(f"# verify alpha core: {alpha[HEAD:-TAIL]}", file=sys.stderr)
    print(f"# verify beta core: {beta[HEAD:-TAIL]}", file=sys.stderr)


if __name__ == "__main__":
    main()
