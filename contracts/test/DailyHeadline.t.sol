// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {Test, console2} from "forge-std/Test.sol";
import {DailyHeadline} from "../src/DailyHeadline.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";

contract DailyHeadlineTest is Test {
    DailyHeadline public nft;
    
    // Create dummy addresses for testing
    address public owner = makeAddr("owner");
    address public hacker = makeAddr("hacker");

    function setUp() public {
        // Deploy a fresh contract before every test
        nft = new DailyHeadline(owner);
    }


    function test_Deployment() public view {
        assertEq(nft.name(), "Daily Headline");
        assertEq(nft.symbol(), "DHL");
        assertEq(nft.owner(), owner);
    }

    function test_MintAsOwner() public {
        vm.prank(owner); // Simulates the owner making the call
        nft.mint();
        
        assertEq(nft.ownerOf(1), owner);
    }

    function test_UpdateURIAsOwner() public {
        vm.startPrank(owner);
        nft.mint();
        
        string memory newURI = "ipfs://QmTestHash12345";
        nft.updateTokenURI(newURI);
        
        // Verify the state actually changed
        assertEq(nft.tokenURI(1), newURI);
        vm.stopPrank();
    }


    function test_RevertWhen_MintAsStranger() public {
        vm.prank(hacker); 
        // We expect OpenZeppelin 5.0's exact custom error to be thrown
        vm.expectRevert(abi.encodeWithSelector(Ownable.OwnableUnauthorizedAccount.selector, hacker));
        nft.mint();
    }

    function test_RevertWhen_UpdateURIAsStranger() public {
        vm.prank(hacker);
        vm.expectRevert(abi.encodeWithSelector(Ownable.OwnableUnauthorizedAccount.selector, hacker));
        nft.updateTokenURI("ipfs://QmHackedURI");
    }
}