-- Initial seed data for YurTube.
-- Safe to run multiple times (uses ON CONFLICT DO NOTHING).
-- Inserts default categories and a few tags.

-- Categories (YouTube-like set)
INSERT INTO categories (category_id, name, created_at) VALUES
('cat01', 'Film & Animation', NOW()),
('cat02', 'Autos & Vehicles', NOW()),
('cat03', 'Music', NOW()),
('cat04', 'Pets & Animals', NOW()),
('cat05', 'Sports', NOW()),
('cat06', 'Travel & Events', NOW()),
('cat07', 'Gaming', NOW()),
('cat08', 'People & Blogs', NOW()),
('cat09', 'Comedy', NOW()),
('cat10', 'Entertainment', NOW()),
('cat11', 'News & Politics', NOW()),
('cat12', 'Howto & Style', NOW()),
('cat13', 'Education', NOW()),
('cat14', 'Science & Technology', NOW()),
('cat15', 'Nonprofits & Activism', NOW())
ON CONFLICT (name) DO NOTHING;

-- Tags (example set)
INSERT INTO tags (tag_id, name, created_at) VALUES
('tag01', 'tutorial', NOW()),
('tag02', 'review', NOW()),
('tag03', 'vlog', NOW()),
('tag04', 'music', NOW()),
('tag05', 'gaming', NOW())
ON CONFLICT (name) DO NOTHING;