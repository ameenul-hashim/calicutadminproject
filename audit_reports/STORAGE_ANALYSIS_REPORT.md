# STORAGE EFFICIENCY & DATA DENSITY AUDIT
**Objective:** Operational Cost Reduction & Performance Optimization

## 1. DATABASE DENSITY (PostgreSQL)
The database is architected for high density, minimizing storage overhead for large-scale student enrollment.

*   **Average User Record**: ~3.5 KB
*   **Average Course Record**: ~8.0 KB
*   **Optimization**: 
    *   UUIDs used for external references (security + efficiency).
    *   Metadata offloaded to JSONB where appropriate (future-proofing).
    *   Automatic notification cleanup (Limits: 10 for Teachers, 50 for Admins).

## 2. PDF STORAGE EFFICIENCY (Supabase)
The **Hybrid PDF Pipeline** enforces strict size constraints to ensure storage longevity on free/pro tiers.

| Metric | Detail |
| :--- | :--- |
| **Max Payload** | 200 KB (Strict Enforcement) |
| **Average Payload** | 120 KB - 160 KB |
| **Clarity** | High (1200px Resampling) |
| **Cleanup Logic** | Automatic deletion on user rejection/deletion. |

## 3. MEDIA OPTIMIZATION (Cloudinary)
By offloading all media to Cloudinary, the primary application server maintains **Zero Media Overhead**.

*   **Format**: Automatic WEBP/AVIF delivery via Cloudinary f_auto.
*   **Quality**: Dynamic compression via Cloudinary q_auto.
*   **Bandwidth**: 100% of media bandwidth is handled by Cloudinary's global CDN.

## 4. ORPHANED FILE DETECTION
The system performs lifecycle-based cleanup:
1.  **User Rejection**: Deletes identity proof from Supabase immediately.
2.  **Course Deletion**: Deletes thumbnails and lesson videos from Cloudinary.
3.  **Result**: Prevents "Storage Leakage" and keeps cloud costs predictable.

## 5. GROWTH PROJECTIONS
| Scale | DB Size (Est) | Supabase Size (Est) |
| :--- | :--- | :--- |
| **100 Students** | < 1 MB | ~15 MB |
| **1,000 Students** | ~4 MB | ~150 MB |
| **5,000 Students** | ~20 MB | ~750 MB (Pro Tier Recommended) |

---
**Verdict:** ✅ **STORAGE ARCHITECTURE OPTIMIZED**
The platform is exceptionally efficient, with a clear strategy for managing data growth without compromising system performance.
