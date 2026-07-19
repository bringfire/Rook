using System;
using System.Collections.Generic;
using Rhino.Geometry;

public class Script_Instance
{
    public void RunScript(out object Boxes)
    {
        int countX = 10;
        int countY = 10;
        double spacing = 2.0;
        double sizeX = 1.0;
        double sizeY = 1.0;
        double minHeight = 1.0;
        double maxHeight = 10.0;

        double startX = -(countX - 1) * spacing / 2.0;
        double startY = -(countY - 1) * spacing / 2.0;
        double maxR = Math.Sqrt(startX * startX + startY * startY);
        List<Box> boxes = new List<Box>();

        for (int i = 0; i < countX; i++)
        {
            for (int j = 0; j < countY; j++)
            {
                double cx = startX + i * spacing;
                double cy = startY + j * spacing;
                double r = Math.Sqrt(cx * cx + cy * cy);
                double normalizedR = maxR > 0 ? r / maxR : 0;
                double h = minHeight + (maxHeight - minHeight) * normalizedR;
                BoundingBox bbox = new BoundingBox(
                    new Point3d(cx - sizeX / 2.0, cy - sizeY / 2.0, 0.0),
                    new Point3d(cx + sizeX / 2.0, cy + sizeY / 2.0, h)
                );
                boxes.Add(new Box(bbox));
            }
        }

        Boxes = boxes;
    }
}
