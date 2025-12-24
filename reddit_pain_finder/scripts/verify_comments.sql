-- Comments Table Verification Script
-- Run this to verify the comments table is working correctly

.mode column
.headers on

-- Test 1: Check if comments table exists
SELECT '=== Test 1: Comments Table Exists ===' as "";
SELECT name FROM sqlite_master WHERE type='table' AND name='comments';

-- Test 2: Count total comments
SELECT '=== Test 2: Total Comment Count ===' as "";
SELECT COUNT(*) as total_comments FROM comments;

-- Test 3: Count posts with comments
SELECT '=== Test 3: Posts With Comments ===' as "";
SELECT COUNT(DISTINCT post_id) as posts_with_comments FROM comments;

-- Test 4: Comments by source
SELECT '=== Test 4: Comments By Source ===' as "";
SELECT source, COUNT(*) as count, AVG(score) as avg_score FROM comments GROUP BY source;

-- Test 5: Sample comments with post titles
SELECT '=== Test 5: Sample Comments ===' as "";
SELECT
    p.source,
    substr(p.title, 1, 30) as title_preview,
    substr(c.body, 1, 50) as comment_preview,
    c.score
FROM posts p
JOIN comments c ON p.id = c.post_id
ORDER BY c.score DESC
LIMIT 10;

-- Test 6: Check indexes
SELECT '=== Test 6: Indexes on Comments Table ===' as "";
SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='comments';

SELECT '=== All Tests Complete ===' as "";
