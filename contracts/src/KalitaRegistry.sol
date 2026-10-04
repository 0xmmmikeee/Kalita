// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

/// @title KalitaRegistry
/// @notice Tamper-evident history of curated wallet lists.
///
/// Kalita ranks the wallets that buy on a launchpad bonding curve by their out-of-sample edge and
/// keeps a list per strategy profile. A list is only worth following if its history cannot be
/// rewritten: a publisher must not be able to add yesterday's winners today, or quietly drop the
/// wallets that stopped working. So every daily snapshot of a list is committed here as the
/// Merkle root of its members, together with the list size and how many wallets were added and
/// removed. Anyone can later prove that a wallet was (or was not claimed to be) in the list on a
/// given day, and compare the list's performance strictly after each snapshot.
///
/// Design choices (same as TrackRecord, the sister contract for strategy decisions):
///   - no owner, no admin, no upgrade path, no funds held;
///   - snapshots of one list are strictly ordered by `asOf`, so the record is a single timeline;
///   - leaves and inner nodes are domain-separated (0x00 / 0x01 prefix) and pairs are sorted.
contract KalitaRegistry {
    struct List {
        address owner;
        uint64 createdAt;
        uint64 closedAt; // 0 while active
        uint64 lastAsOf; // asOf of the latest snapshot
        uint32 snapshots;
        bytes32 rulesHash; // hash of the published selection rules / code version
        string name; // e.g. "fast" or "picker"
    }

    struct Snapshot {
        bytes32 root; // Merkle root over leafHash(wallet) of every member
        uint32 size; // number of members
        uint32 added; // members not present in the previous snapshot
        uint32 removed; // members of the previous snapshot no longer present
        uint64 asOf; // data cut-off the list was computed from (unix seconds)
        uint64 publishedAt;
    }

    List[] private _lists;
    mapping(uint256 => Snapshot[]) private _snapshots;
    mapping(uint256 => mapping(address => bool)) public isPublisher;
    mapping(address => uint256[]) private _byOwner;

    event ListRegistered(uint256 indexed id, address indexed owner, bytes32 rulesHash, string name);
    event PublisherSet(uint256 indexed id, address indexed publisher, bool allowed);
    event SnapshotPublished(
        uint256 indexed id, uint256 indexed index, bytes32 root, uint32 size, uint32 added, uint32 removed, uint64 asOf, string uri
    );
    event RulesUpdated(uint256 indexed id, bytes32 rulesHash, string uri);
    event ListClosed(uint256 indexed id, uint64 closedAt);

    error NotOwner();
    error NotPublisher();
    error UnknownList();
    error ListIsClosed();
    error EmptySnapshot();
    error BadAsOf();
    error BadDelta();
    error EmptyName();

    modifier exists(uint256 id) {
        if (id >= _lists.length) revert UnknownList();
        _;
    }

    modifier onlyOwner(uint256 id) {
        if (id >= _lists.length) revert UnknownList();
        if (_lists[id].owner != msg.sender) revert NotOwner();
        _;
    }

    modifier active(uint256 id) {
        if (_lists[id].closedAt != 0) revert ListIsClosed();
        _;
    }

    // ---------------------------------------------------------------- writes

    /// @notice Register a list. Registration is permanent and public.
    function registerList(string calldata name, bytes32 rulesHash) external returns (uint256 id) {
        if (bytes(name).length == 0) revert EmptyName();
        id = _lists.length;
        _lists.push(
            List({
                owner: msg.sender,
                createdAt: uint64(block.timestamp),
                closedAt: 0,
                lastAsOf: 0,
                snapshots: 0,
                rulesHash: rulesHash,
                name: name
            })
        );
        _byOwner[msg.sender].push(id);
        emit ListRegistered(id, msg.sender, rulesHash, name);
    }

    /// @notice Allow another address (for example the daily job's hot key) to publish snapshots.
    function setPublisher(uint256 id, address publisher, bool allowed) external onlyOwner(id) {
        isPublisher[id][publisher] = allowed;
        emit PublisherSet(id, publisher, allowed);
    }

    /// @notice Record that the selection rules changed. The old snapshots keep their meaning.
    function updateRules(uint256 id, bytes32 rulesHash, string calldata uri) external onlyOwner(id) active(id) {
        _lists[id].rulesHash = rulesHash;
        emit RulesUpdated(id, rulesHash, uri);
    }

    /// @notice Publish the list as of `asOf`. `asOf` must be later than the previous snapshot and
    /// not in the future. `uri` points to the full member list and proofs off chain.
    function publishSnapshot(
        uint256 id,
        bytes32 root,
        uint32 size,
        uint32 added,
        uint32 removed,
        uint64 asOf,
        string calldata uri
    ) external exists(id) active(id) returns (uint256 index) {
        List storage l = _lists[id];
        if (msg.sender != l.owner && !isPublisher[id][msg.sender]) revert NotPublisher();
        if (size == 0 || root == bytes32(0)) revert EmptySnapshot();
        if (asOf > block.timestamp || asOf < l.createdAt || asOf <= l.lastAsOf) revert BadAsOf();
        // the first snapshot adds everyone; later ones cannot add more than they contain
        if (l.snapshots == 0) {
            if (added != size || removed != 0) revert BadDelta();
        } else {
            Snapshot storage prev = _snapshots[id][l.snapshots - 1];
            if (added > size || removed > prev.size || prev.size + added - removed != size) revert BadDelta();
        }
        index = _snapshots[id].length;
        _snapshots[id].push(
            Snapshot({root: root, size: size, added: added, removed: removed, asOf: asOf, publishedAt: uint64(block.timestamp)})
        );
        l.lastAsOf = asOf;
        l.snapshots += 1;
        emit SnapshotPublished(id, index, root, size, added, removed, asOf, uri);
    }

    /// @notice Close a list for good. It stays visible; no further snapshots are accepted.
    function closeList(uint256 id) external onlyOwner(id) active(id) {
        _lists[id].closedAt = uint64(block.timestamp);
        emit ListClosed(id, uint64(block.timestamp));
    }

    // ---------------------------------------------------------------- reads

    function listCount() external view returns (uint256) {
        return _lists.length;
    }

    function getList(uint256 id) external view exists(id) returns (List memory) {
        return _lists[id];
    }

    /// @notice All lists ever registered by `owner`, closed ones included.
    function listsOf(address owner) external view returns (uint256[] memory) {
        return _byOwner[owner];
    }

    function snapshotCount(uint256 id) external view exists(id) returns (uint256) {
        return _snapshots[id].length;
    }

    function getSnapshot(uint256 id, uint256 index) external view exists(id) returns (Snapshot memory) {
        return _snapshots[id][index];
    }

    /// @notice Latest snapshot of a list (reverts if none).
    function latest(uint256 id) external view exists(id) returns (Snapshot memory) {
        return _snapshots[id][_snapshots[id].length - 1];
    }

    /// @notice Was `wallet` a member of snapshot `index` of list `id`?
    function verifyMember(uint256 id, uint256 index, address wallet, bytes32[] calldata proof)
        external
        view
        exists(id)
        returns (bool)
    {
        if (index >= _snapshots[id].length) return false;
        return processProof(proof, leafHash(wallet)) == _snapshots[id][index].root;
    }

    // ---------------------------------------------------------------- merkle helpers (pure)

    function leafHash(address wallet) public pure returns (bytes32) {
        return keccak256(abi.encodePacked(bytes1(0x00), wallet));
    }

    function nodeHash(bytes32 a, bytes32 b) public pure returns (bytes32) {
        return a < b
            ? keccak256(abi.encodePacked(bytes1(0x01), a, b))
            : keccak256(abi.encodePacked(bytes1(0x01), b, a));
    }

    function processProof(bytes32[] calldata proof, bytes32 leaf) public pure returns (bytes32 h) {
        h = leaf;
        for (uint256 i = 0; i < proof.length; i++) {
            h = nodeHash(h, proof[i]);
        }
    }
}
