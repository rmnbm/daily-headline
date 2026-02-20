// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {ERC721} from "@openzeppelin/contracts/token/ERC721/ERC721.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";

/**
 * @title DailyHeadline
 * @dev Single ERC721 token representing the daily NYT headline.
 * The token URI is updated daily via an off-chain automation script.
 */
contract DailyHeadline is ERC721, Ownable {
    uint256 public constant TOKEN_ID = 1;
    string private _currentURI;

    event URIUpdated(string newURI, uint256 timestamp);

    constructor(address initialOwner) ERC721("Daily Headline", "DHL") Ownable(initialOwner) {}

    /**
     * @dev Mints the single dynamic token.
     * Restricted to contract owner.
     */
    function mint() external onlyOwner {
        _safeMint(msg.sender, TOKEN_ID);
    }

    /**
     * @dev Updates the metadata URI for the token.
     * Intended to be called by the backend automation wallet daily.
     * @param newURI The IPFS URI containing the new metadata.
     */
    function updateTokenURI(string calldata newURI) external onlyOwner {
        _currentURI = newURI;
        emit URIUpdated(newURI, block.timestamp);
    }

    /**
     * @dev Returns the current active URI for the token.
     */
    function tokenURI(uint256 tokenId) public view override returns (string memory) {
        _requireOwned(tokenId); // Reverts if token hasn't been minted (OpenZeppelin 5.x)
        return _currentURI;
    }
}