// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

import {Test} from "forge-std/Test.sol";
import {KalitaRegistry} from "../src/KalitaRegistry.sol";

contract KalitaRegistryTest is Test {
    KalitaRegistry reg;
    address alice = address(0xA11CE);
    address bob = address(0xB0B);
    address job = address(0x30B);
    uint64 T0 = 1_790_000_000;

    function setUp() public {
        vm.warp(T0);
        reg = new KalitaRegistry();
    }

    // -------- helpers: the same tree the off-chain tool (src/registry_snapshot.py) builds --------
    function _root(address[] memory members) internal view returns (bytes32) {
        bytes32[] memory level = new bytes32[](members.length);
        for (uint256 i; i < members.length; i++) level[i] = reg.leafHash(members[i]);
        while (level.length > 1) {
            bytes32[] memory next = new bytes32[]((level.length + 1) / 2);
            for (uint256 i; i < level.length; i += 2) {
                next[i / 2] = i + 1 < level.length ? reg.nodeHash(level[i], level[i + 1]) : level[i];
            }
            level = next;
        }
        return level[0];
    }

    function _proof(address[] memory members, uint256 idx) internal view returns (bytes32[] memory proof) {
        bytes32[] memory level = new bytes32[](members.length);
        for (uint256 i; i < members.length; i++) level[i] = reg.leafHash(members[i]);
        bytes32[] memory tmp = new bytes32[](32);
        uint256 n;
        while (level.length > 1) {
            uint256 sib = idx ^ 1;
            if (sib < level.length) tmp[n++] = level[sib];
            bytes32[] memory next = new bytes32[]((level.length + 1) / 2);
            for (uint256 i; i < level.length; i += 2) {
                next[i / 2] = i + 1 < level.length ? reg.nodeHash(level[i], level[i + 1]) : level[i];
            }
            level = next;
            idx /= 2;
        }
        proof = new bytes32[](n);
        for (uint256 i; i < n; i++) proof[i] = tmp[i];
    }

    function _members(uint256 n, uint256 seed) internal pure returns (address[] memory m) {
        m = new address[](n);
        for (uint256 i; i < n; i++) m[i] = address(uint160(uint256(keccak256(abi.encodePacked("wallet", seed, i)))));
    }

    function _register() internal returns (uint256 id) {
        vm.prank(alice);
        id = reg.registerList("fast", keccak256("rules-v1"));
    }

    // -------- registration --------
    function test_register() public {
        uint256 id = _register();
        assertEq(id, 0);
        KalitaRegistry.List memory l = reg.getList(id);
        assertEq(l.owner, alice);
        assertEq(l.createdAt, block.timestamp);
        assertEq(l.rulesHash, keccak256("rules-v1"));
        assertEq(l.snapshots, 0);
        assertEq(reg.listCount(), 1);
        assertEq(reg.listsOf(alice).length, 1);
    }

    function test_register_emptyNameReverts() public {
        vm.expectRevert(KalitaRegistry.EmptyName.selector);
        reg.registerList("", bytes32(0));
    }

    // -------- snapshots --------
    function test_firstSnapshot_addsEveryone() public {
        uint256 id = _register();
        address[] memory m = _members(7, 1);
        bytes32 r_m = _root(m);
        vm.warp(T0 + 1 days);
        vm.prank(alice);
        uint256 idx = reg.publishSnapshot(id, r_m, 7, 7, 0, T0 + 1 days - 60, "ipfs://x");
        assertEq(idx, 0);
        KalitaRegistry.Snapshot memory s = reg.getSnapshot(id, 0);
        assertEq(s.size, 7);
        assertEq(s.added, 7);
        assertEq(s.removed, 0);
        assertEq(s.asOf, T0 + 1 days - 60);
        assertEq(s.publishedAt, block.timestamp);
        assertEq(reg.snapshotCount(id), 1);
        assertEq(reg.latest(id).root, r_m);
    }

    function test_firstSnapshot_badDeltaReverts() public {
        uint256 id = _register();
        address[] memory m = _members(3, 1);
        bytes32 r_m = _root(m);
        vm.warp(T0 + 1);
        vm.startPrank(alice);
        vm.expectRevert(KalitaRegistry.BadDelta.selector);
        reg.publishSnapshot(id, r_m, 3, 2, 0, T0 + 1, "");
        vm.expectRevert(KalitaRegistry.BadDelta.selector);
        reg.publishSnapshot(id, r_m, 3, 3, 1, T0 + 1, "");
        vm.stopPrank();
    }

    function test_snapshot_deltaMustBalance() public {
        uint256 id = _register();
        address[] memory a = _members(10, 1);
        bytes32 r_a = _root(a);
        address[] memory b = _members(12, 2);
        bytes32 r_b = _root(b);
        vm.startPrank(alice);
        vm.warp(T0 + 1);
        reg.publishSnapshot(id, r_a, 10, 10, 0, T0 + 1, "");
        vm.warp(T0 + 2);
        // 10 + added - removed must equal 12
        vm.expectRevert(KalitaRegistry.BadDelta.selector);
        reg.publishSnapshot(id, r_b, 12, 3, 0, T0 + 2, "");
        vm.expectRevert(KalitaRegistry.BadDelta.selector);
        reg.publishSnapshot(id, r_b, 12, 13, 11, T0 + 2, ""); // added > size
        vm.expectRevert(KalitaRegistry.BadDelta.selector);
        reg.publishSnapshot(id, r_b, 12, 12, 11, T0 + 2, ""); // removed > prev.size
        uint256 idx = reg.publishSnapshot(id, r_b, 12, 5, 3, T0 + 2, "");
        assertEq(idx, 1);
        vm.stopPrank();
    }

    function test_snapshot_asOfMustAdvance() public {
        uint256 id = _register();
        address[] memory a = _members(4, 1);
        bytes32 r_a = _root(a);
        vm.startPrank(alice);
        vm.warp(T0 + 100);
        reg.publishSnapshot(id, r_a, 4, 4, 0, T0 + 50, "");
        vm.expectRevert(KalitaRegistry.BadAsOf.selector);
        reg.publishSnapshot(id, r_a, 4, 0, 0, T0 + 50, ""); // same asOf
        vm.expectRevert(KalitaRegistry.BadAsOf.selector);
        reg.publishSnapshot(id, r_a, 4, 0, 0, T0 + 40, ""); // earlier
        vm.expectRevert(KalitaRegistry.BadAsOf.selector);
        reg.publishSnapshot(id, r_a, 4, 0, 0, T0 + 101, ""); // future
        reg.publishSnapshot(id, r_a, 4, 0, 0, T0 + 60, "");
        vm.stopPrank();
        assertEq(reg.snapshotCount(id), 2);
    }

    function test_snapshot_emptyReverts() public {
        uint256 id = _register();
        vm.warp(T0 + 1);
        vm.startPrank(alice);
        vm.expectRevert(KalitaRegistry.EmptySnapshot.selector);
        reg.publishSnapshot(id, bytes32(0), 1, 1, 0, T0 + 1, "");
        vm.expectRevert(KalitaRegistry.EmptySnapshot.selector);
        reg.publishSnapshot(id, keccak256("x"), 0, 0, 0, T0 + 1, "");
        vm.stopPrank();
    }

    function test_onlyOwnerOrPublisher() public {
        uint256 id = _register();
        address[] memory a = _members(2, 1);
        bytes32 r_a = _root(a);
        vm.warp(T0 + 1);
        vm.prank(bob);
        vm.expectRevert(KalitaRegistry.NotPublisher.selector);
        reg.publishSnapshot(id, r_a, 2, 2, 0, T0 + 1, "");
        vm.prank(bob);
        vm.expectRevert(KalitaRegistry.NotOwner.selector);
        reg.setPublisher(id, job, true);
        vm.prank(alice);
        reg.setPublisher(id, job, true);
        vm.prank(job);
        reg.publishSnapshot(id, r_a, 2, 2, 0, T0 + 1, "");
        assertEq(reg.snapshotCount(id), 1);
    }

    function test_unknownList() public {
        vm.expectRevert(KalitaRegistry.UnknownList.selector);
        reg.getList(0);
        vm.expectRevert(KalitaRegistry.UnknownList.selector);
        reg.publishSnapshot(0, keccak256("x"), 1, 1, 0, T0, "");
    }

    function test_close() public {
        uint256 id = _register();
        address[] memory a = _members(2, 1);
        bytes32 r_a = _root(a);
        vm.prank(bob);
        vm.expectRevert(KalitaRegistry.NotOwner.selector);
        reg.closeList(id);
        vm.prank(alice);
        reg.closeList(id);
        assertEq(reg.getList(id).closedAt, block.timestamp);
        vm.warp(T0 + 1);
        vm.prank(alice);
        vm.expectRevert(KalitaRegistry.ListIsClosed.selector);
        reg.publishSnapshot(id, r_a, 2, 2, 0, T0 + 1, "");
        vm.prank(alice);
        vm.expectRevert(KalitaRegistry.ListIsClosed.selector);
        reg.closeList(id);
    }

    function test_updateRules() public {
        uint256 id = _register();
        vm.prank(alice);
        reg.updateRules(id, keccak256("rules-v2"), "https://kalita.tech/rules/v2");
        assertEq(reg.getList(id).rulesHash, keccak256("rules-v2"));
    }

    // -------- membership proofs --------
    function test_verifyMember() public {
        uint256 id = _register();
        address[] memory m = _members(13, 7);
        bytes32 r_m = _root(m);
        vm.warp(T0 + 1);
        vm.prank(alice);
        reg.publishSnapshot(id, r_m, 13, 13, 0, T0 + 1, "");
        for (uint256 i; i < m.length; i++) {
            assertTrue(reg.verifyMember(id, 0, m[i], _proof(m, i)), "member should verify");
        }
        address stranger = address(0x5717A);
        assertFalse(reg.verifyMember(id, 0, stranger, _proof(m, 0)));
        assertFalse(reg.verifyMember(id, 1, m[0], _proof(m, 0)), "unknown snapshot index");
    }

    function test_verifyMember_singleMember() public {
        uint256 id = _register();
        address[] memory m = _members(1, 3);
        bytes32 r_m = _root(m);
        vm.warp(T0 + 1);
        vm.prank(alice);
        reg.publishSnapshot(id, r_m, 1, 1, 0, T0 + 1, "");
        bytes32[] memory empty;
        assertTrue(reg.verifyMember(id, 0, m[0], empty));
        assertEq(reg.latest(id).root, reg.leafHash(m[0]));
    }

    function testFuzz_verifyMember(uint8 n, uint8 pick, uint256 seed) public {
        n = uint8(bound(n, 1, 64));
        pick = uint8(bound(pick, 0, n - 1));
        uint256 id = _register();
        address[] memory m = _members(n, seed);
        bytes32 r_m = _root(m);
        vm.warp(T0 + 1);
        vm.prank(alice);
        reg.publishSnapshot(id, r_m, n, n, 0, T0 + 1, "");
        assertTrue(reg.verifyMember(id, 0, m[pick], _proof(m, pick)));
    }

    // -------- test vector shared with the off-chain tool --------
    function test_vector() public {
        address[] memory m = new address[](3);
        m[0] = 0x1111111111111111111111111111111111111111;
        m[1] = 0x2222222222222222222222222222222222222222;
        m[2] = 0x3333333333333333333333333333333333333333;
        bytes32 l0 = keccak256(abi.encodePacked(bytes1(0x00), m[0]));
        assertEq(reg.leafHash(m[0]), l0);
        bytes32 root = _root(m);
        // printed by: python3 src/registry_snapshot.py --vector
        emit log_named_bytes32("root(3 fixed addresses)", root);
        // the same root the Python tool prints — the two implementations must never drift apart
        assertEq(root, 0x8e0d4c6ac47820266d23291bdc6c013383b4d3a8984b56e1b61738b7f649a1c1);
        assertTrue(reg.processProof(_proof(m, 2), reg.leafHash(m[2])) == root);
    }
}
